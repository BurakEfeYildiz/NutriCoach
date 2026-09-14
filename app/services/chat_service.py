"""Short DB sessions surround, but never span, remote model calls."""
from datetime import datetime
from time import perf_counter

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

import re

from app.core.config import Settings
from app.models.chat import AIRequest, Conversation, Message
from app.models.user import utc_now
from app.schemas.chat import ConversationRead, GroundingSource, MessageCreate, MessageRead, MessageResult
from app.schemas.intents import IntentPlan, NutritionQuestion
from app.schemas.memory import MemoryExtractionResult
from app.services.chat_actions import ClarificationNeeded, apply_actions
from app.services.context_service import build_coach_context
from app.services.gemini_service import GeminiProvider, ProviderError, ProviderResult
from app.services.memory_service import deactivate_memory_by_key, persist_candidate, should_extract_memories
from app.services.nutrition import daily_summary, weekly_summary
from app.services.users import get_user

SEARCH_INDICATORS = {
    # Current / live event keywords
    "bugünkü", "güncel", "son dakika", "kaç kaç", "maçı", "skoru", "skor", "maç sonucu",
    "araştırma", "araştırmalar", "rehberi",
    # Common restaurant / coffee / fast-food / packaged food brands & delivery
    "coffy", "starbucks", "mcdonald", "mcdonalds", "burger king", "kfc",
    "subway", "domino", "dominos", "pizza hut", "algida", "ülker", "eti",
    "pınar", "sütaş", "torku", "dunkin", "popeyes", "arby", "tavuk dünyası",
    "krispy kreme", "caribou", "danone", "nutella", "nestle", "kinder",
    "snickers", "coca cola", "pepsi", "red bull", "migros", "getir", "trendyol",
    "marka", "markası", "markaları",
    # Explicit search phrases
    "internetten bak", "internetten ara", "internette ara", "araştır",
    "google'da ara", "web'den kontrol et", "web'de ara", "çevrimiçi ara",
}


def should_use_search(text: str) -> bool:
    lowered = text.lower().replace("İ", "i").replace("I", "ı")
    return any(indicator in lowered for indicator in SEARCH_INDICATORS)


class ChatService:
    def __init__(self, sessions: sessionmaker, provider: GeminiProvider, settings: Settings):
        self.sessions = sessions
        self.provider = provider
        self.settings = settings

    def redact(self, content: str) -> str:
        secret = self.settings.gemini_api_key
        value = secret.get_secret_value() if secret else ''
        return content.replace(value, '[REDACTED]') if value else content

    @staticmethod
    def owned_conversation(session: Session, user_id: str, conversation_id: str) -> Conversation:
        conversation = session.scalar(select(Conversation).where(Conversation.user_id == user_id, Conversation.id == conversation_id))
        if conversation is None:
            raise HTTPException(404, 'Sohbet bulunamadı.')
        return conversation

    def create_conversation(self, user_id: str) -> ConversationRead:
        with self.sessions() as session:
            get_user(session, user_id)
            conversation = Conversation(user_id=user_id)
            session.add(conversation)
            session.commit()
            return ConversationRead.model_validate(conversation)

    def list_conversations(self, user_id: str, limit: int, offset: int) -> list[ConversationRead]:
        with self.sessions() as session:
            get_user(session, user_id)
            rows = session.scalars(select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.created_at.desc(), Conversation.id).limit(limit).offset(offset))
            return [ConversationRead.model_validate(row) for row in rows]

    def get_conversation(self, user_id: str, conversation_id: str) -> ConversationRead:
        with self.sessions() as session:
            return ConversationRead.model_validate(self.owned_conversation(session, user_id, conversation_id))

    def list_messages(self, user_id: str, conversation_id: str, limit: int, offset: int) -> list[MessageRead]:
        with self.sessions() as session:
            self.owned_conversation(session, user_id, conversation_id)
            rows = session.scalars(select(Message).where(Message.user_id == user_id, Message.conversation_id == conversation_id).order_by(Message.created_at, Message.id).limit(limit).offset(offset))
            return [MessageRead.model_validate(row) for row in rows]

    @staticmethod
    def result(session: Session, message: Message) -> MessageResult:
        reply = session.scalar(select(Message).where(Message.user_id == message.user_id, Message.conversation_id == message.conversation_id, Message.in_reply_to == message.id))
        return MessageResult(user_message=MessageRead.model_validate(message), assistant_message=MessageRead.model_validate(reply) if reply else None)

    def claim(self, user_id: str, conversation_id: str, data: MessageCreate) -> tuple[MessageResult, bool]:
        with self.sessions() as session:
            self.owned_conversation(session, user_id, conversation_id)
            content = self.redact(data.content)
            message = Message(user_id=user_id, conversation_id=conversation_id, role='user', content=content, client_request_id=str(data.client_request_id))
            session.add(message)
            try:
                session.commit()
                return self.result(session, message), True
            except IntegrityError:
                session.rollback()
                existing = session.scalar(select(Message).where(Message.user_id == user_id, Message.client_request_id == str(data.client_request_id)))
                if existing is None:
                    raise HTTPException(409, 'Mesaj kaydedilemedi.') from None
                if existing.conversation_id != conversation_id or existing.content != content:
                    raise HTTPException(409, 'client_request_id başka bir içerik veya sohbet için kullanılmış.') from None
                # Includes pending/failed states: never re-execute a claimed request.
                return self.result(session, existing), False

    def input_payload(self, user_id: str, conversation_id: str, message_id: str, text: str, now: datetime) -> dict:
        with self.sessions() as session:
            user = get_user(session, user_id)
            rows = list(session.scalars(select(Message).where(
                Message.user_id == user_id, Message.conversation_id == conversation_id,
                Message.id != message_id, Message.status == 'completed', Message.created_at <= now,
            ).order_by(Message.created_at.desc(), Message.id.desc()).limit(self.settings.chat_recent_messages)))
            remaining = self.settings.chat_history_chars
            history = []
            for row in rows:
                content = self.redact(row.content)[:remaining]
                if not content:
                    break
                history.append({'role': row.role, 'content': content})
                remaining -= len(content)
            return {'now': now.isoformat(), 'timezone': user.timezone, 'recent_messages': list(reversed(history)), 'current_message': text}

    def call(self, user_id: str, message_id: str, phase: str, payload: dict, enable_search: bool = False) -> tuple[IntentPlan | str, list[dict]]:
        with self.sessions() as session:
            log = AIRequest(user_id=user_id, message_id=message_id, model=self.redact(self.provider.model)[:200], phase=phase)
            session.add(log)
            session.commit()
            log_id = log.id
        started = perf_counter()
        result: ProviderResult | None = None
        failure: ProviderError | None = None
        parsed = None
        try:
            result = self.provider.extract_intent(payload) if phase == 'intent' else self.provider.generate_reply(payload, enable_search=enable_search)
            output = self.redact(result.text)
            if not output.strip() or len(output) > (64000 if phase == 'intent' else 8000):
                raise ProviderError('invalid_output')
            parsed = IntentPlan.model_validate_json(output) if phase == 'intent' else output
        except ValidationError:
            failure = ProviderError('invalid_output')
        except ProviderError as error:
            failure = error
        except TimeoutError:
            failure = ProviderError('timeout')
        except Exception:
            failure = ProviderError('provider_error')
        elapsed = max(0, int((perf_counter() - started) * 1000))
        with self.sessions() as session:
            log = session.scalar(select(AIRequest).where(AIRequest.user_id == user_id, AIRequest.id == log_id))
            log.status = 'failed' if failure else 'completed'
            log.error_type = failure.kind if failure else None
            log.latency_ms = elapsed
            if result is not None:
                for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                    value = getattr(result.usage, key)
                    setattr(log, key, value if isinstance(value, int) and value >= 0 else None)
            session.commit()
        if failure:
            raise failure
        sources = getattr(result, 'grounding_sources', None) or []
        return parsed, sources

    def finish(
        self,
        user_id: str,
        message_id: str,
        content: str,
        error_type: str | None = None,
        grounding_sources: list[dict] | None = None,
    ) -> MessageResult:
        with self.sessions() as session:
            message = session.scalar(select(Message).where(Message.user_id == user_id, Message.id == message_id))
            status = 'failed' if error_type else 'completed'
            message.status = status
            message.error_type = error_type
            conversation = self.owned_conversation(session, user_id, message.conversation_id)
            conversation.updated_at = utc_now()
            session.add(Message(user_id=user_id, conversation_id=message.conversation_id, role='assistant',
                                content=self.redact(content), status=status, in_reply_to=message.id, error_type=error_type))
            session.commit()
            res = self.result(session, message)
            if grounding_sources:
                sources = [GroundingSource(title=s.get('title') or 'Web Kaynağı', url=s.get('url')) for s in grounding_sources if s.get('url')]
                res.grounding_sources = sources
                if res.assistant_message:
                    res.assistant_message.grounding_sources = sources
            return res

    def process(self, user_id: str, conversation_id: str, data: MessageCreate) -> tuple[MessageResult, bool]:
        snapshot, is_new = self.claim(user_id, conversation_id, data)
        if not is_new:
            return snapshot, False
        message = snapshot.user_message
        effects_committed = False
        try:
            payload = self.input_payload(user_id, conversation_id, message.id, message.content, message.created_at)
            plan, _ = self.call(user_id, message.id, 'intent', payload)
            if plan.needs_clarification:
                return self.finish(user_id, message.id, plan.clarification_question), True
            with self.sessions() as session:
                actions = apply_actions(session, user_id, plan, message.created_at, message.content)
                stored = session.scalar(select(Message).where(Message.user_id == user_id, Message.id == message.id))
                stored.effects_committed = bool(actions)
                stored.action_results = [action.model_dump() for action in actions]
                session.commit()  # Effects and durable receipt commit together, before coaching.
                effects_committed = bool(actions)
            try:
                self.process_memories(user_id, message.id, message.content)
            except Exception:
                pass
            with self.sessions() as session:
                coach_context = build_coach_context(
                    session=session,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message_id=message.id,
                    current_message=message.content,
                    now=message.created_at,
                    plan=plan,
                    action_results=stored.action_results,
                    settings=self.settings,
                )
                coach_payload = {
                    'current_user_message': message.content,
                    'current_message': message.content,
                    'action_results': [action.model_dump() for action in actions],
                    'coach_context': coach_context.model_dump(mode='json'),
                    # Backward compatibility for Phase 3 tests/consumers:
                    'today': daily_summary(session, user_id, now=message.created_at).model_dump(mode='json'),
                }
                if any(isinstance(action, NutritionQuestion) for action in plan.actions):
                    coach_payload['last_7_days'] = weekly_summary(session, user_id, now=message.created_at).model_dump(mode='json')
            enable_search = should_use_search(message.content)
            reply, sources = self.call(user_id, message.id, 'coach', coach_payload, enable_search=enable_search)
            return self.finish(user_id, message.id, reply, grounding_sources=sources), True
        except ClarificationNeeded as error:
            return self.finish(user_id, message.id, str(error)), True
        except ProviderError as error:
            if effects_committed:
                content = 'Kayıt değişiklikleri kaydedildi fakat AI cevabı alınamadı. Aynı isteği tekrar göndermek kayıtları çoğaltmaz.'
            else:
                content = 'AI isteği tamamlanamadı; beslenme kayıtlarında değişiklik yapılmadı.'
            return self.finish(user_id, message.id, content, error.kind), True
        except (ValidationError, HTTPException, SQLAlchemyError):
            content = 'Kayıtlar korundu fakat cevap tamamlanamadı.' if effects_committed else 'İşlemler uygulanamadı; beslenme kayıtlarında değişiklik yapılmadı.'
            return self.finish(user_id, message.id, content, 'action_error'), True

    def process_memories(self, user_id: str, message_id: str, content: str) -> None:
        lower = content.lower()
        if 'unut' in lower:
            match = re.search(r'(?:şunu\s+unut|unut(?:\s*:)?)\s*:?\s*([\wçğıöşü\s]+)', lower)
            target = match.group(1).strip() if match else lower.replace('unut', '').strip()
            if target:
                with self.sessions() as session:
                    deactivate_memory_by_key(session, user_id, target)
                    session.commit()

        if not should_extract_memories(content):
            return

        result = self.provider.extract_memories({'message': content})
        output = self.redact(result.text)
        if not output.strip():
            return
        parsed = MemoryExtractionResult.model_validate_json(output)
        if not parsed.candidates:
            return

        with self.sessions() as session:
            for candidate in parsed.candidates:
                persist_candidate(
                    session,
                    user_id,
                    candidate,
                    source_message_id=message_id,
                    min_confidence=self.settings.memory_min_confidence,
                )
            session.commit()


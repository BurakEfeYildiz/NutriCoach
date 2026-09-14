from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.routes.nutrition import Limit, Offset
from app.schemas.chat import ConversationRead, MessageCreate, MessageRead, MessageResult
from app.services.chat_service import ChatService

router = APIRouter(prefix='/users/{user_id}/conversations', tags=['chat (local development)'])


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


Chat = Annotated[ChatService, Depends(get_chat_service)]


@router.post('', response_model=ConversationRead, status_code=201)
def create_conversation(user_id: UUID, chat: Chat):
    return chat.create_conversation(str(user_id))


@router.get('', response_model=list[ConversationRead])
def list_conversations(user_id: UUID, chat: Chat, limit: Limit = 100, offset: Offset = 0):
    return chat.list_conversations(str(user_id), limit, offset)


@router.get('/{conversation_id}', response_model=ConversationRead)
def get_conversation(user_id: UUID, conversation_id: UUID, chat: Chat):
    return chat.get_conversation(str(user_id), str(conversation_id))


@router.post('/{conversation_id}/messages', response_model=MessageResult, status_code=201)
def create_message(user_id: UUID, conversation_id: UUID, data: MessageCreate, chat: Chat, response: Response):
    result, created = chat.process(str(user_id), str(conversation_id), data)
    response.status_code = 202 if result.user_message.status == 'pending' else (201 if created else 200)
    return result


@router.get('/{conversation_id}/messages', response_model=list[MessageRead])
def list_messages(user_id: UUID, conversation_id: UUID, chat: Chat, limit: Limit = 100, offset: Offset = 0):
    return chat.list_messages(str(user_id), str(conversation_id), limit, offset)

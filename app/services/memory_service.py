"""Long-Term Memory service: extraction pre-filter, deduplication, contradiction handling and persistence."""
from datetime import datetime
from decimal import Decimal
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.models.user import utc_now
from app.schemas.memory import MemoryCandidate

PREFILTER_PATTERNS = (
    # Preferences / dislikes
    'sevmiyorum', 'seviyorum', 'severim', 'sevmem', 'nefret', 'bayılırım', 'tercih', 'hoşlanmam', 'hoşlanırım',
    # Routines / frequency
    'genelde', 'çoğunlukla', 'her gün', 'haftada', 'her hafta', 'her sabah', 'her akşam', 'asla', 'hiçbir zaman', 'rutinim', 'alışkanlığım',
    # Practical constraints
    'vaktim olmuyor', 'vaktim yok', 'zamanım yok', 'fırsat bulamıyorum', 'hazırlayamıyorum', 'evde yemek',
    # Dietary exclusions / habits
    'yemem', 'içmem', 'tüketmem', 'yapmam', 'alerjim', 'intoleransım', 'alerji', 'vejetaryen', 'vegan', 'oruç',
    # Explicit commands
    'hatırla', 'unut', 'not al', 'kaydet',
    # English equivalents
    'i like', 'i don\'t like', 'i love', 'i hate', 'prefer', 'usually', 'always', 'never', 'routine', 'habit', 'allergic', 'allergy', 'remember', 'forget',
)

SENSITIVE_PATTERNS = (
    'password', 'şifre', 'sifre', 'parola', 'kredi kartı', 'kredi karti', 'iban', 'hesap no',
    'tc kimlik', 'ev adresim', 'adresim', 'passport', 'pasaport',
    'kanser', 'kemoterapi', 'depresyon', 'antidepresan', 'bipolar', 'şizofreni', 'sizofreni',
    'ilaç', 'ilac', 'reçete', 'recete', 'diyabet', 'diyabetik', 'metformin', 'insülin', 'insulin',
    'tansiyon', 'hastalık', 'hastalik', 'teşhis', 'teshis', 'tedavi',
    'parti', 'seçim', 'secim', 'dinim', 'mezhep',
)

CANONICAL_PROFILE_KEYS = {
    'calorie_target', 'kalori_hedefi', 'protein_target', 'carb_target', 'fat_target',
    'height', 'boy', 'weight_goal', 'hedef_kilo', 'birth_date', 'dogum_tarihi', 'yas', 'age',
}

OPPOSING_CATEGORIES = {
    'food_preference': 'food_dislike',
    'food_dislike': 'food_preference',
}


def should_extract_memories(message_text: str) -> bool:
    lower = message_text.lower()
    return any(p in lower for p in PREFILTER_PATTERNS)


def normalize_key(key: str) -> str:
    cleaned = key.strip().lower()
    # Replace Turkish special characters with standard ascii counterparts for stable canonical keys
    tr_map = str.maketrans('çğıöşü', 'cgiosu')
    normalized = cleaned.translate(tr_map)
    # Replace spaces and dashes with underscore, remove other non-alphanumeric chars
    slug = re.sub(r'[\s\-]+', '_', re.sub(r'[^a-z0-9\s\-]', '', normalized))
    return slug[:100] if slug else 'item'


def is_sensitive_candidate(candidate: MemoryCandidate) -> bool:
    text = f"{candidate.key} {candidate.value} {candidate.evidence}".lower()
    if any(pattern in text for pattern in SENSITIVE_PATTERNS):
        return True
    norm_key = normalize_key(candidate.key)
    if norm_key in CANONICAL_PROFILE_KEYS:
        return True
    return False


def persist_candidate(
    session: Session,
    user_id: str,
    candidate: MemoryCandidate,
    source_message_id: str | None = None,
    min_confidence: Decimal = Decimal('0.60'),
) -> Memory | None:
    if candidate.confidence < min_confidence:
        return None

    if is_sensitive_candidate(candidate):
        return None

    norm_key = normalize_key(candidate.key)
    now = utc_now()

    # 1. Handle Contradictions / Supersession
    # If this candidate is in an opposing category (e.g. food_preference vs food_dislike) for the same key,
    # supersede the old opposing memory.
    opposing_cat = OPPOSING_CATEGORIES.get(candidate.category)
    if opposing_cat:
        opposing_memories = list(session.scalars(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.category == opposing_cat,
                Memory.key == norm_key,
                Memory.status == 'active',
            )
        ))
        for old_mem in opposing_memories:
            old_mem.status = 'superseded'
            old_mem.updated_at = now

    # 2. Deduplication: Look for existing active memory with same category and normalized key
    existing = session.scalar(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.category == candidate.category,
            Memory.key == norm_key,
            Memory.status == 'active',
        )
    )

    if existing:
        existing.value = candidate.value
        existing.confidence = candidate.confidence
        existing.last_confirmed_at = now
        existing.updated_at = now
        if source_message_id:
            existing.source_message_id = source_message_id
        return existing

    # 3. Create new active memory
    memory = Memory(
        user_id=user_id,
        category=candidate.category,
        key=norm_key,
        value=candidate.value,
        status='active',
        confidence=candidate.confidence,
        source_message_id=source_message_id,
        created_at=now,
        updated_at=now,
        last_confirmed_at=now,
    )
    session.add(memory)
    return memory


def list_active_memories(
    session: Session,
    user_id: str,
    categories: list[str] | None = None,
    limit: int = 100,
) -> list[Memory]:
    query = select(Memory).where(Memory.user_id == user_id, Memory.status == 'active')
    if categories:
        query = query.where(Memory.category.in_(categories))
    query = query.order_by(Memory.last_confirmed_at.desc(), Memory.created_at.desc()).limit(limit)
    return list(session.scalars(query))


def deactivate_memory(session: Session, user_id: str, memory_id: str) -> bool:
    memory = session.scalar(
        select(Memory).where(Memory.user_id == user_id, Memory.id == memory_id, Memory.status == 'active')
    )
    if memory is None:
        return False
    memory.status = 'deleted'
    memory.updated_at = utc_now()
    return True


def deactivate_memory_by_key(session: Session, user_id: str, key_query: str) -> list[Memory]:
    norm = normalize_key(key_query)
    tokens = [t for t in norm.split('_') if len(t) >= 3]
    now = utc_now()
    all_active = list_active_memories(session, user_id)
    deactivated = []
    for mem in all_active:
        if mem.key in norm or norm in mem.key or any(token in mem.key or mem.key in token for token in tokens):
            mem.status = 'deleted'
            mem.updated_at = now
            deactivated.append(mem)
    return deactivated

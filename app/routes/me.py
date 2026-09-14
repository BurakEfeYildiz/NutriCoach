from datetime import date
import io
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.models.user import User
from app.routes.dependencies import (
    Database,
    get_settings,
    require_current_user,
    verify_csrf,
)
from app.routes.nutrition import Limit, Offset
from app.schemas.auth import ChangePasswordRequest
from app.schemas.chat import ConversationRead, MessageCreate, MessageRead, MessageResult
from app.schemas.meal_image import MealImageAnalysisResult
from app.schemas.memory import MemoryRead
from app.schemas.nutrition import (
    DaySummary,
    MealRead,
    MealReplace,
    MealWrite,
    WeekSummary,
    WeightRead,
    WeightWrite,
)
from app.schemas.user import ProfileRead, ProfileWrite, UserRead
from app.services import auth_service, memory_service, nutrition, users, weights
from app.services.chat_service import ChatService

router = APIRouter(prefix="/me", tags=["me"])
CurrentUser = Annotated[User, Depends(require_current_user)]
CSRF = Depends(verify_csrf)


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


Chat = Annotated[ChatService, Depends(get_chat_service)]


# --- Identity & Profile ---

@router.get("", response_model=UserRead)
def get_me(user: CurrentUser):
    return user


@router.get("/profile", response_model=ProfileRead)
def get_my_profile(user: CurrentUser, session: Database):
    return users.get_user(session, user.id).profile


@router.put("/profile", response_model=ProfileRead, dependencies=[CSRF])
def replace_my_profile(data: ProfileWrite, user: CurrentUser, session: Database):
    return users.replace_profile(session, user.id, data)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CSRF])
def change_password(
    data: ChangePasswordRequest,
    user: CurrentUser,
    session: Database,
    request: Request,
):
    settings = get_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    auth_service.change_user_password(
        session=session,
        user=user,
        current_password=data.current_password,
        new_password=data.new_password,
        current_raw_token=raw_token,
    )
    return None


# --- Nutrition & Meals ---

@router.post("/meals/analyze-photo", response_model=MealImageAnalysisResult, dependencies=[CSRF])
async def analyze_meal_photo(
    request: Request,
    user: CurrentUser,
    file: UploadFile = File(...),
):
    if not file.content_type or file.content_type.lower() not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Desteklenmeyen dosya türü. Yalnızca JPEG, PNG ve WebP desteklenir.",
        )

    content = await file.read()
    max_size = 10 * 1024 * 1024  # 10 MB
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Dosya boyutu 10 MB sınırını aşıyor.",
        )

    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz veya bozuk görsel dosyası.",
        )

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    max_dim = 1600
    if max(img.width, img.height) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    out_buf = io.BytesIO()
    img.save(out_buf, format="JPEG", quality=85)
    processed_bytes = out_buf.getvalue()

    provider = getattr(request.app.state, "provider", None)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI sağlayıcısı yapılandırılmamış.",
        )

    provider_result = provider.analyze_meal_image(processed_bytes, "image/jpeg")

    try:
        result = MealImageAnalysisResult.model_validate_json(provider_result.text)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Görsel analizi sonucu doğrulanamadı.",
        )

    return result


@router.post("/meals", response_model=MealRead, status_code=status.HTTP_201_CREATED, dependencies=[CSRF])
def create_my_meal(data: MealWrite, user: CurrentUser, session: Database):
    return nutrition.meal_read(nutrition.create_meal(session, user.id, data))


@router.get("/meals", response_model=list[MealRead])
def list_my_meals(
    user: CurrentUser,
    session: Database,
    day: date | None = None,
    limit: Limit = 100,
    offset: Offset = 0,
):
    return [nutrition.meal_read(meal) for meal in nutrition.list_meals(session, user.id, day, limit, offset)]


@router.get("/meals/today", response_model=list[MealRead])
def today_my_meals(user: CurrentUser, session: Database, limit: Limit = 100, offset: Offset = 0):
    return [
        nutrition.meal_read(meal)
        for meal in nutrition.list_meals(session, user.id, nutrition.local_date(user), limit, offset)
    ]


@router.get("/meals/{meal_id}", response_model=MealRead)
def get_my_meal(meal_id: UUID, user: CurrentUser, session: Database):
    return nutrition.meal_read(nutrition.owned_meal(session, user.id, str(meal_id)))


@router.put("/meals/{meal_id}", response_model=MealRead, dependencies=[CSRF])
def replace_my_meal(meal_id: UUID, data: MealReplace, user: CurrentUser, session: Database):
    return nutrition.meal_read(nutrition.replace_meal(session, user.id, str(meal_id), data))


@router.delete("/meals/{meal_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CSRF])
def delete_my_meal(meal_id: UUID, user: CurrentUser, session: Database):
    nutrition.delete_meal(session, user.id, str(meal_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/nutrition/daily", response_model=DaySummary)
def my_daily_nutrition(user: CurrentUser, session: Database, day: date | None = None):
    return nutrition.daily_summary(session, user.id, day)


@router.get("/nutrition/weekly", response_model=WeekSummary)
def my_weekly_nutrition(user: CurrentUser, session: Database, end_day: date | None = None):
    return nutrition.weekly_summary(session, user.id, end_day)


# --- Weights ---

@router.post("/weight-logs", response_model=WeightRead, status_code=status.HTTP_201_CREATED, dependencies=[CSRF])
def create_my_weight(data: WeightWrite, user: CurrentUser, session: Database):
    return weights.create_weight(session, user.id, data)


@router.get("/weight-logs", response_model=list[WeightRead])
def list_my_weights(user: CurrentUser, session: Database, limit: Limit = 100, offset: Offset = 0):
    return weights.list_weights(session, user.id, limit, offset)


@router.get("/weight-logs/current", response_model=WeightRead)
def my_current_weight(user: CurrentUser, session: Database):
    return weights.current_weight(session, user.id)


@router.delete("/weight-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CSRF])
def delete_my_weight(log_id: UUID, user: CurrentUser, session: Database):
    weights.delete_weight(session, user.id, str(log_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Chat & Conversations ---

@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED, dependencies=[CSRF])
def create_my_conversation(user: CurrentUser, chat: Chat):
    return chat.create_conversation(user.id)


@router.get("/conversations", response_model=list[ConversationRead])
def list_my_conversations(user: CurrentUser, chat: Chat, limit: Limit = 100, offset: Offset = 0):
    return chat.list_conversations(user.id, limit, offset)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_my_conversation(conversation_id: UUID, user: CurrentUser, chat: Chat):
    return chat.get_conversation(user.id, str(conversation_id))


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CSRF],
)
def create_my_message(
    conversation_id: UUID,
    data: MessageCreate,
    user: CurrentUser,
    chat: Chat,
    response: Response,
):
    result, created = chat.process(user.id, str(conversation_id), data)
    response.status_code = 202 if result.user_message.status == "pending" else (201 if created else 200)
    return result


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_my_messages(
    conversation_id: UUID,
    user: CurrentUser,
    chat: Chat,
    limit: Limit = 100,
    offset: Offset = 0,
):
    return chat.list_messages(user.id, str(conversation_id), limit, offset)


# --- Long-Term Memories ---

@router.get("/memories", response_model=list[MemoryRead])
def list_my_memories(
    user: CurrentUser,
    session: Database,
    include_inactive: bool = False,
    limit: int = 100,
):
    query = select(Memory).where(Memory.user_id == user.id)
    if not include_inactive:
        query = query.where(Memory.status == "active")
    query = query.order_by(Memory.last_confirmed_at.desc(), Memory.created_at.desc()).limit(limit)
    rows = list(session.scalars(query))
    return [MemoryRead.model_validate(row) for row in rows]


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CSRF])
def delete_my_memory(memory_id: UUID, user: CurrentUser, session: Database):
    success = memory_service.deactivate_memory(session, user.id, str(memory_id))
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hafıza kaydı bulunamadı.")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

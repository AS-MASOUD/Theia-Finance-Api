import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.database.models import UserModel
from src.app.database.session import get_db_session
from src.modules.ai.application.dtos import (
    ChatMessageRequest,
    ConversationResponse,
    MessageResponse,
)
from src.modules.ai.application.services import AIService
from src.modules.auth.presentation.dependencies import get_current_user

ai_router = APIRouter(prefix="/ai", tags=["AI Financial Assistant"])


def get_ai_service(db: AsyncSession = Depends(get_db_session)) -> AIService:
    return AIService(db)


@ai_router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: UserModel = Depends(get_current_user),
    service: AIService = Depends(get_ai_service),
) -> list[ConversationResponse]:
    convos = await service.list_conversations()
    return [ConversationResponse.model_validate(c) for c in convos]


@ai_router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: UserModel = Depends(get_current_user),
    service: AIService = Depends(get_ai_service),
) -> ConversationResponse:
    convo = await service.get_conversation(conversation_id)
    return ConversationResponse.model_validate(convo)


@ai_router.post("/chat", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def chat(
    payload: ChatMessageRequest,
    current_user: UserModel = Depends(get_current_user),
    service: AIService = Depends(get_ai_service),
) -> MessageResponse:
    return await service.process_chat(payload, current_user=current_user)

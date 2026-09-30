from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.gemini_client import GeminiConfigurationError, LazyGeminiProvider
from app.database import get_db
from app.auth import AuthenticatedUser, get_current_user
from app.schemas.assistant_chat import ChatRequest, ChatResponse
from app.services.assistant_chat import chat


router = APIRouter(prefix="/api/assistant", tags=["assistant chat"])


def get_chat_provider() -> LazyGeminiProvider:
    return LazyGeminiProvider()


@router.post("/chat", response_model=ChatResponse)
def chat_message(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    provider: LazyGeminiProvider = Depends(get_chat_provider),
    user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return chat(db, provider, payload, user_id=user.sub)
    except GeminiConfigurationError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Trợ lý chưa được cấu hình. Vui lòng liên hệ người quản trị.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Trợ lý đang tạm thời không phản hồi. Mẹ thử lại sau nhé.",
        ) from exc

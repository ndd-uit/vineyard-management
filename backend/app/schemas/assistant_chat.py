from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

from app.schemas.assistant_actions import PendingActionPreview


class ChatResponseType(str, Enum):
    MESSAGE = "MESSAGE"
    CLARIFICATION = "CLARIFICATION"
    ACTION_PREVIEW = "ACTION_PREVIEW"
    QUERY_RESULT = "QUERY_RESULT"
    ACTION_EXECUTED = "ACTION_EXECUTED"


ChatText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    message: ChatText


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: ChatText
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=12)
    pending_action: PendingActionPreview | None = None


class ChatResponse(BaseModel):
    type: ChatResponseType
    message: str
    pending_action: PendingActionPreview | None = None
    data: Any | None = None

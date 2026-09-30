from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import AuthenticatedUser, get_current_user
from app.schemas.assistant_actions import (
    PendingActionPreview,
    QueryResult,
    ReadAction,
    WriteAction,
)
from app.services import assistant_actions


router = APIRouter(prefix="/api/assistant", tags=["assistant actions"])


@router.post("/actions/preview", response_model=PendingActionPreview)
def preview_action(
    payload: WriteAction,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    return assistant_actions.preview(db, payload, user_id=user.sub)


@router.post("/query", response_model=QueryResult)
def query_action(payload: ReadAction, db: Session = Depends(get_db)):
    return assistant_actions.query(db, payload)

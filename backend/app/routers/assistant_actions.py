from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.assistant_actions import (
    ActionExecutionResult,
    PendingActionPreview,
    QueryResult,
    ReadAction,
    WriteAction,
)
from app.services import assistant_actions


router = APIRouter(prefix="/api/assistant", tags=["assistant actions"])


@router.post("/actions/preview", response_model=PendingActionPreview)
def preview_action(payload: WriteAction, db: Session = Depends(get_db)):
    return assistant_actions.preview(db, payload)


@router.post("/actions/execute", response_model=ActionExecutionResult)
def execute_action(payload: WriteAction, db: Session = Depends(get_db)):
    return assistant_actions.execute(db, payload)


@router.post("/query", response_model=QueryResult)
def query_action(payload: ReadAction, db: Session = Depends(get_db)):
    return assistant_actions.query(db, payload)

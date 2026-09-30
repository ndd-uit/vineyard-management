"""Atomically claim and execute one confirmed assistant preview."""

import hmac
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.models.assistant_action_execution import AssistantActionExecution
from app.schemas.assistant_actions import ActionExecutionResult, PendingActionPreview, WriteAction
from app.services import action_tokens, assistant_actions


def _claim(db: Session, user_id: str, pending: PendingActionPreview, action: WriteAction, digest: str) -> bool:
    table = AssistantActionExecution.__table__
    values = dict(
        user_id=user_id,
        idempotency_key=pending.idempotency_key,
        action_name=action.action,
        payload_hash=digest,
        result_json=None,
    )
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgresql.insert(table).values(**values)
    elif dialect == "sqlite":  # Isolated tests only; concurrency must be tested on PostgreSQL.
        statement = sqlite.insert(table).values(**values)
    else:
        raise RuntimeError("Assistant idempotency requires PostgreSQL")
    statement = statement.on_conflict_do_nothing(
        index_elements=["user_id", "idempotency_key"]
    ).returning(table.c.idempotency_key)
    return db.scalar(statement) is not None


def execute_confirmed(
    db: Session, *, user_id: str, pending: PendingActionPreview, action: WriteAction
) -> tuple[ActionExecutionResult | None, bool]:
    """Return (result, duplicate); None means an incomplete claim needs a safe retry."""
    digest = action_tokens.payload_hash(action)
    with db.begin():
        if _claim(db, user_id, pending, action, digest):
            result = assistant_actions.execute_uncommitted(db, action)
            row = db.get(AssistantActionExecution, (user_id, pending.idempotency_key))
            if row is None:
                raise RuntimeError("Assistant execution claim disappeared")
            row.result_json = result.model_dump(mode="json")
            row.completed_at = datetime.now(UTC)
            db.flush()
            return result, False

        row = db.scalar(select(AssistantActionExecution).where(
            AssistantActionExecution.user_id == user_id,
            AssistantActionExecution.idempotency_key == pending.idempotency_key,
        ))
        if row is None:
            return None, True
        if row.action_name != action.action or not hmac.compare_digest(row.payload_hash, digest):
            raise HTTPException(status.HTTP_409_CONFLICT, "Assistant action identity does not match")
        if row.result_json is None or row.completed_at is None:
            return None, True
        return ActionExecutionResult.model_validate(row.result_json), True

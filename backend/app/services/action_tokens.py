"""Canonical assistant payloads and stable, user-bound preview signatures."""

import hashlib
import hmac
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.schemas.assistant_actions import WriteAction


PREVIEW_LIFETIME = timedelta(minutes=15)
TOKEN_VERSION = "v1"


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _encoded(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_action(action: WriteAction) -> bytes:
    return _encoded({
        "action": action.action,
        "arguments": _canonical(action.arguments.model_dump(exclude_none=True)),
    })


def payload_hash(action: WriteAction) -> str:
    return hashlib.sha256(canonical_action(action)).hexdigest()


def _signing_key() -> bytes:
    value = os.getenv("ASSISTANT_ACTION_SIGNING_KEY", "")
    key = value.encode("utf-8")
    if len(key) < 32 or value == "replace_with_long_random_secret":
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Trợ lý chưa thể xác nhận lúc này. Mẹ thử lại sau nhé.",
        )
    return key


def new_preview_identity() -> tuple[UUID, datetime]:
    return uuid4(), datetime.now(UTC).replace(microsecond=0) + PREVIEW_LIFETIME


def action_token(
    action: WriteAction, *, user_id: str, idempotency_key: UUID, expires_at: datetime
) -> str:
    if expires_at.tzinfo is None:
        raise ValueError("Preview expiry must include a timezone")
    signed_payload = _encoded({
        "version": TOKEN_VERSION,
        "user_id": user_id,
        "idempotency_key": str(idempotency_key),
        "expires_at": int(expires_at.timestamp()),
        "action": json.loads(canonical_action(action)),
    })
    digest = hmac.new(_signing_key(), signed_payload, hashlib.sha256).hexdigest()
    return f"{TOKEN_VERSION}.{digest}"


def token_matches(
    action: WriteAction, token: str, *, user_id: str,
    idempotency_key: UUID, expires_at: datetime,
) -> bool:
    if expires_at.tzinfo is None or datetime.now(UTC) >= expires_at:
        return False
    expected = action_token(
        action, user_id=user_id, idempotency_key=idempotency_key, expires_at=expires_at
    )
    return hmac.compare_digest(expected, token)

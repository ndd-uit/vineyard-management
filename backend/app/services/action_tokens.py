"""Process-local protection for confirmed assistant actions.

This is intentionally not cross-instance idempotency. A persistent store or
database constraint is required before running multiple backend instances.
"""

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from app.schemas.assistant_actions import WriteAction


_SIGNING_KEY = secrets.token_bytes(32)


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


def action_token(action: WriteAction) -> str:
    payload = {
        "action": action.action,
        "arguments": _canonical(action.arguments.model_dump(exclude_none=True)),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(_SIGNING_KEY, encoded, hashlib.sha256).hexdigest()


def token_matches(action: WriteAction, token: str) -> bool:
    return hmac.compare_digest(action_token(action), token)


class RecentActionCache:
    def __init__(self, max_entries: int = 512, ttl_seconds: int = 300) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._executed: OrderedDict[str, float] = OrderedDict()
        self._in_progress: set[str] = set()

    def _prune(self, now: float) -> None:
        while self._executed:
            _, timestamp = next(iter(self._executed.items()))
            if now - timestamp <= self.ttl_seconds:
                break
            self._executed.popitem(last=False)

    def begin(self, token: str) -> str:
        with self._lock:
            self._prune(time.monotonic())
            if token in self._executed:
                return "executed"
            if token in self._in_progress:
                return "in_progress"
            self._in_progress.add(token)
            return "new"

    def finish(self, token: str) -> None:
        with self._lock:
            self._in_progress.discard(token)
            self._executed[token] = time.monotonic()
            self._executed.move_to_end(token)
            while len(self._executed) > self.max_entries:
                self._executed.popitem(last=False)

    def release(self, token: str) -> None:
        with self._lock:
            self._in_progress.discard(token)


recent_actions = RecentActionCache()

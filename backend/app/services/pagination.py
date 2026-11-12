from __future__ import annotations

import base64
import json
from datetime import datetime

from app.core.errors import InvalidCursorError


def encode_cursor(created_at: datetime, item_id: str) -> str:
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": item_id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        payload = json.loads(raw)
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        item_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise InvalidCursorError("Cursor de paginación inválido") from exc
    if not item_id:
        raise InvalidCursorError("Cursor de paginación inválido")
    return created_at, item_id

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from app.schemas.exercise import GenerateResponse


@dataclass
class _CacheEntry:
    value: GenerateResponse
    expires_at: float


class GenerationCache:
    """LRU + TTL en memoria. Suficiente para una app local de un proceso."""

    def __init__(self, *, max_entries: int = 64, ttl_seconds: int = 900) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> GenerateResponse | None:
        if self.max_entries <= 0 or self.ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return entry.value.model_copy(deep=True)

    def set(self, key: str, value: GenerateResponse) -> None:
        if self.max_entries <= 0 or self.ttl_seconds <= 0:
            return
        with self._lock:
            self._entries[key] = _CacheEntry(
                value=value.model_copy(deep=True),
                expires_at=time.monotonic() + self.ttl_seconds,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

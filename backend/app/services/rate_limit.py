import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowRateLimiter:
    """Rate limiter en memoria por clave (usuario, token o IP).

    Suficiente para una app local-first de un solo proceso. No usa Redis para
    no añadir infraestructura; si algún día hay varios workers, se sustituye por
    un backend compartido.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(0.1, window_seconds)
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        """Devuelve (permitido, segundos_de_espera_recomendados)."""
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            if len(self._events) > 10_000:
                self._prune(cutoff)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def _prune(self, cutoff: float) -> None:
        stale = [key for key, bucket in self._events.items() if not bucket or bucket[-1] <= cutoff]
        for key in stale:
            self._events.pop(key, None)

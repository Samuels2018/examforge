import logging
import time

from app.core.errors import EmbeddingUnavailableError
from app.services.embeddings.base import EmbeddingBatch, EmbeddingProvider

logger = logging.getLogger(__name__)


class AutoEmbeddingProvider(EmbeddingProvider):
    """Usa Ollama si responde y cae al embedding local determinista."""

    name = "auto"

    def __init__(self, primary: EmbeddingProvider, fallback: EmbeddingProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self._checked_at = 0.0
        self._primary_available = False

    @property
    def cache_key(self) -> str:
        if self._check_primary():
            return self.primary.cache_key
        return self.fallback.cache_key

    def _check_primary(self) -> bool:
        now = time.monotonic()
        if now - self._checked_at > 5:
            self._primary_available = self.primary.available()
            self._checked_at = now
        return self._primary_available

    def available(self) -> bool:
        return True

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if self._check_primary():
            try:
                return self.primary.embed(texts)
            except EmbeddingUnavailableError as exc:
                logger.warning("Embeddings de Ollama fallaron; usando offline: %s", exc)
        return self.fallback.embed(texts)

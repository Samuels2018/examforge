from app.core.config import Settings
from app.services.embeddings.auto import AutoEmbeddingProvider
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.offline import OfflineEmbeddingProvider
from app.services.embeddings.ollama import OllamaEmbeddingProvider


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    offline = OfflineEmbeddingProvider(dimensions=settings.offline_embedding_dimensions)
    if settings.embedding_provider == "offline":
        return offline

    ollama = OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embedding_model,
        timeout_seconds=min(settings.ollama_timeout_seconds, 60),
    )
    if settings.embedding_provider == "ollama":
        return ollama
    return AutoEmbeddingProvider(primary=ollama, fallback=offline)

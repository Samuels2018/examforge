from app.core.config import Settings
from app.services.llm.auto import AutoProvider
from app.services.llm.base import LLMProvider
from app.services.llm.offline import OfflineProvider
from app.services.llm.ollama import OllamaProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "offline":
        return OfflineProvider()

    ollama = OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    if settings.llm_provider == "ollama":
        return ollama
    return AutoProvider(primary=ollama, fallback=OfflineProvider())

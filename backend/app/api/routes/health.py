from fastapi import APIRouter, Depends, Request

from app.api.deps import get_settings
from app.core.config import Settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    provider_mode = settings.llm_provider
    configured_provider = request.app.state.llm_provider_factory().name
    queue = getattr(request.app.state, "processing_queue", None)
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "llm_mode": provider_mode,
        "llm_provider": configured_provider,
        "model": settings.ollama_model if provider_mode != "offline" else None,
        "background_queue_depth": queue.depth if queue is not None else 0,
    }

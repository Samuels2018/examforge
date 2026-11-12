import asyncio
import json
import logging
import queue
import threading
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_embedding_provider,
    get_generation_cache,
    get_generation_registry,
    get_llm_provider,
    get_session,
    get_settings,
    require_workspace,
)
from app.core.config import Settings
from app.core.errors import AppError, GenerationCancelledError, NotFoundError
from app.models import User
from app.models.enums import Difficulty, ExerciseKind
from app.repositories.exercises import get_exercise, list_attempt_history, list_exercises
from app.repositories.metrics import generation_metrics_summary, list_generation_metrics
from app.schemas.common import Page
from app.schemas.exercise import (
    AttemptCreate,
    AttemptHistoryItem,
    AttemptResult,
    ExerciseRead,
    GenerateRequest,
    GenerateResponse,
)
from app.schemas.guide import GuideRead
from app.schemas.metrics import GenerationMetricRead, GenerationMetricsRead
from app.services.embeddings.base import EmbeddingProvider
from app.services.generation import GenerationService
from app.services.generation_cache import GenerationCache
from app.services.generation_registry import GenerationRegistry
from app.services.grading import AttemptService
from app.services.guides import GuideService
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}",
    tags=["exercises"],
    dependencies=[Depends(require_workspace)],
)


@router.post(
    "/exercises/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_exercises(
    workspace_id: str,
    payload: GenerateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    cache: GenerationCache | None = Depends(get_generation_cache),
) -> GenerateResponse:
    return GenerationService(session, settings, provider, embedder, cache).generate(
        workspace_id, payload
    )


@router.post("/exercises/generate/stream")
async def stream_exercises(
    workspace_id: str,
    payload: GenerateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    registry: GenerationRegistry = Depends(get_generation_registry),
    cache: GenerationCache | None = Depends(get_generation_cache),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    if not settings.streaming_enabled:
        raise AppError("El streaming está desactivado en la configuración")

    handle = registry.create(workspace_id)
    events: queue.Queue[tuple[str, dict]] = queue.Queue()

    def worker() -> None:
        session = request.app.state.session_factory()
        session.info["owner_id"] = user.id
        try:
            result = GenerationService(
                session, settings, provider, embedder, cache
            ).generate(
                workspace_id,
                payload,
                cancel_event=handle.cancel_event,
                progress=lambda stage, message: events.put(
                    ("progress", {"stage": stage, "message": message})
                ),
            )
            events.put(("result", result.model_dump(mode="json")))
        except GenerationCancelledError as exc:
            events.put(("cancelled", {"message": exc.message}))
        except AppError as exc:
            events.put(("error", {"code": exc.code, "message": exc.message}))
        except Exception:
            logger.exception("Fallo inesperado durante la generación en streaming")
            events.put(
                (
                    "error",
                    {
                        "code": "internal_error",
                        "message": "No se pudo completar la generación",
                    },
                )
            )
        finally:
            session.close()
            registry.finish(handle.id)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("start", {"generation_id": handle.id})
        try:
            while True:
                if await request.is_disconnected():
                    handle.cancel_event.set()
                    return
                try:
                    kind, data = events.get_nowait()
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    await asyncio.sleep(0.1)
                    continue
                yield _sse(kind, data)
                if kind in {"result", "error", "cancelled"}:
                    return
        finally:
            handle.cancel_event.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Generation-Id": handle.id,
        },
    )


@router.post(
    "/exercises/generate/{generation_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_generation(
    workspace_id: str,
    generation_id: str,
    registry: GenerationRegistry = Depends(get_generation_registry),
) -> None:
    if not registry.cancel(workspace_id, generation_id):
        raise NotFoundError("Generación no encontrada o ya finalizada")


@router.get("/exercises", response_model=Page[ExerciseRead])
def list_workspace_exercises(
    workspace_id: str,
    difficulty: Difficulty | None = None,
    kind: ExerciseKind | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
) -> Page[ExerciseRead]:
    items, total = list_exercises(
        session,
        workspace_id=workspace_id,
        difficulty=difficulty,
        kind=kind,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[ExerciseRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/exercises/{exercise_id}", response_model=ExerciseRead)
def get_workspace_exercise(
    workspace_id: str,
    exercise_id: str,
    session: Session = Depends(get_session),
) -> ExerciseRead:
    exercise = get_exercise(session, workspace_id, exercise_id)
    if exercise is None:
        raise NotFoundError("Ejercicio no encontrado")
    return ExerciseRead.model_validate(exercise)


@router.get("/exercises/{exercise_id}/guide", response_model=GuideRead)
def get_exercise_guide(
    workspace_id: str,
    exercise_id: str,
    session: Session = Depends(get_session),
) -> GuideRead:
    return GuideService(session).get_or_create(workspace_id, exercise_id)


@router.post(
    "/exercises/{exercise_id}/variation",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_variation(
    workspace_id: str,
    exercise_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    cache: GenerationCache | None = Depends(get_generation_cache),
) -> GenerateResponse:
    exercise = get_exercise(session, workspace_id, exercise_id)
    if exercise is None:
        raise NotFoundError("Ejercicio no encontrado")
    payload = GenerateRequest(
        count=1,
        difficulties=[Difficulty(exercise.difficulty)],
        focus=exercise.topic,
    )
    return GenerationService(session, settings, provider, embedder, cache).generate(
        workspace_id, payload
    )


@router.post(
    "/exercises/{exercise_id}/attempts",
    response_model=AttemptResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_attempt(
    workspace_id: str,
    exercise_id: str,
    payload: AttemptCreate,
    session: Session = Depends(get_session),
    provider: LLMProvider = Depends(get_llm_provider),
) -> AttemptResult:
    return AttemptService(session, provider).submit(
        workspace_id=workspace_id,
        exercise_id=exercise_id,
        payload=payload,
    )


@router.get("/attempts", response_model=Page[AttemptHistoryItem])
def list_workspace_attempts(
    workspace_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    session: Session = Depends(get_session),
) -> Page[AttemptHistoryItem]:
    items, total, next_cursor = list_attempt_history(
        session,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        cursor=cursor,
    )
    return Page(
        items=items,
        total=total,
        limit=limit,
        offset=0 if cursor else offset,
        next_cursor=next_cursor,
    )


@router.get("/generation-metrics", response_model=GenerationMetricsRead)
def get_generation_metrics(
    workspace_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    session: Session = Depends(get_session),
) -> GenerationMetricsRead:
    total, cached, average_duration, total_tokens = generation_metrics_summary(
        session, workspace_id=workspace_id
    )
    recent = list_generation_metrics(session, workspace_id=workspace_id, limit=limit)
    return GenerationMetricsRead(
        workspace_id=workspace_id,
        total_generations=total,
        cached_generations=cached,
        cache_hit_rate=round(cached / total, 3) if total else 0.0,
        average_duration_ms=average_duration,
        total_tokens=total_tokens,
        average_tokens=round(total_tokens / total) if total else 0,
        recent=[GenerationMetricRead.model_validate(item) for item in recent],
    )


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"

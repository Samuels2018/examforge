import hashlib
import logging
import threading
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    AppError,
    GenerationCancelledError,
    InvalidMaterialError,
    NotFoundError,
)
from app.models import Exercise, GenerationMetric, new_id
from app.repositories.exercises import existing_exercise_signatures
from app.repositories.materials import ContextRow, get_context_rows
from app.repositories.workspaces import get_workspace
from app.schemas.exercise import ExerciseRead, GenerateRequest, GenerateResponse
from app.schemas.usage import TokenUsage
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.retrieval import ContextRetriever
from app.services.generation_cache import GenerationCache
from app.services.llm.base import LLMProvider
from app.services.prompt_safety import sanitize_focus, sanitize_untrusted_text
from app.services.signatures import exercise_signature
from app.services.token_usage import estimate_generation_usage

logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        provider: LLMProvider,
        embedder: EmbeddingProvider | None = None,
        cache: GenerationCache | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.provider = provider
        self.embedder = embedder
        self.cache = cache
        self._last_context = ""
        self._last_usage: TokenUsage | None = None
        self._last_cache_hit = False

    def generate(
        self,
        workspace_id: str,
        payload: GenerateRequest,
        *,
        cancel_event: threading.Event | None = None,
        progress: Callable[[str, str], None] | None = None,
    ) -> GenerateResponse:
        started = time.perf_counter()
        self._last_context = ""
        self._last_usage = None
        self._last_cache_hit = False
        status = "error"
        error_code: str | None = None
        response: GenerateResponse | None = None
        try:
            response = self._generate(
                workspace_id,
                payload,
                cancel_event=cancel_event,
                progress=progress,
                started=started,
            )
            status = "success"
            return response
        except GenerationCancelledError as exc:
            status = "cancelled"
            error_code = exc.code
            raise
        except AppError as exc:
            error_code = exc.code
            raise
        except Exception:
            error_code = "internal_error"
            raise
        finally:
            self._record_metric(
                workspace_id=workspace_id,
                payload=payload,
                status=status,
                error_code=error_code,
                response=response,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    def _generate(
        self,
        workspace_id: str,
        payload: GenerateRequest,
        *,
        cancel_event: threading.Event | None,
        progress: Callable[[str, str], None] | None,
        started: float,
    ) -> GenerateResponse:
        self._check_cancel(cancel_event)
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")

        self._report(progress, "context", "Recuperando material relevante")
        focus = sanitize_focus(payload.focus)
        rows = self._retrieve_context(workspace_id=workspace_id, focus=focus)
        self._check_cancel(cancel_event)
        if not rows:
            raise InvalidMaterialError(
                "No hay material listo para esta evaluación. Sube un archivo de texto, PDF o DOCX."
            )

        max_context_chars = min(
            self.settings.llm_max_context_chars,
            self.settings.llm_max_prompt_tokens * 4,
        )
        context = _build_context(rows, max_chars=max_context_chars)
        self._last_context = context
        cache_key = self._cache_key(workspace_id, payload, context)
        if self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                self._last_cache_hit = True
                self._last_usage = cached.usage
                cached.cached = True
                cached.duration_ms = int((time.perf_counter() - started) * 1000)
                self._report(progress, "done", "Generación recuperada de caché")
                return cached

        self._report(progress, "generating", "Generando ejercicios con el modelo")
        result = self.provider.generate_exercises(
            context=context,
            count=payload.count,
            difficulties=payload.difficulties,
            focus=focus,
            language=payload.language,
        )
        self._check_cancel(cancel_event)
        self._report(progress, "validating", "Validando y guardando ejercicios")

        usage = result.usage or estimate_generation_usage(
            context=context,
            output_text=result.model_dump_json(),
            model=getattr(self.provider, "model", None),
        )
        self._last_usage = usage

        known_signatures = set(existing_exercise_signatures(self.session, workspace_id))
        source_material_ids = sorted({row.material_id for row in rows})
        entities: list[Exercise] = []
        for generated in result.exercises:
            key = exercise_signature(
                generated.question,
                [option.model_dump() for option in generated.options],
            )
            if key in known_signatures:
                continue
            known_signatures.add(key)
            entities.append(
                Exercise(
                    id=new_id(),
                    workspace_id=workspace_id,
                    topic=generated.topic[:160],
                    difficulty=generated.difficulty.value,
                    kind=generated.kind.value,
                    question=generated.question,
                    options=[option.model_dump() for option in generated.options],
                    correct_answer=generated.correct_answer,
                    explanation=generated.explanation,
                    hint=generated.hint,
                    rubric=generated.rubric,
                    source_material_ids=source_material_ids,
                    signature=key,
                )
            )

        if not entities:
            raise InvalidMaterialError(
                "Los ejercicios generados ya existían. Cambia el foco o pide otro lote."
            )

        self._check_cancel(cancel_event)
        self.session.add_all(entities)
        self.session.commit()
        self._report(progress, "done", "Generación completada")

        warning = result.warning
        if len(entities) < payload.count and not warning:
            warning = (
                f"Se crearon {len(entities)} ejercicios de {payload.count} solicitados. "
                "Prueba con más material o vuelve a generar."
            )

        response = GenerateResponse(
            exercises=[ExerciseRead.model_validate(entity) for entity in entities],
            requested=payload.count,
            created=len(entities),
            provider=result.provider,
            warning=warning,
            duration_ms=int((time.perf_counter() - started) * 1000),
            usage=usage,
        )
        if self.cache is not None:
            self.cache.set(cache_key, response)
        return response

    def _cache_key(
        self, workspace_id: str, payload: GenerateRequest, context: str
    ) -> str:
        context_hash = hashlib.sha256(context.encode("utf-8")).hexdigest()
        raw = (
            f"{workspace_id}|{self.provider.name}|{payload.model_dump_json()}|{context_hash}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _record_metric(
        self,
        *,
        workspace_id: str,
        payload: GenerateRequest,
        status: str,
        error_code: str | None,
        response: GenerateResponse | None,
        duration_ms: int,
    ) -> None:
        usage = response.usage if response is not None else self._last_usage
        provider = response.provider if response is not None else self.provider.name
        model = usage.model if usage is not None else getattr(self.provider, "model", None)
        try:
            self.session.add(
                GenerationMetric(
                    workspace_id=workspace_id,
                    provider=provider,
                    model=model,
                    status=status,
                    error_code=error_code,
                    requested=payload.count,
                    created=response.created if response is not None else 0,
                    cached=self._last_cache_hit,
                    duration_ms=duration_ms,
                    context_chars=len(self._last_context),
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    total_tokens=usage.total_tokens if usage else 0,
                    estimated_tokens=usage.estimated if usage else True,
                )
            )
            self.session.commit()
        except Exception:
            logger.exception("No se pudo guardar la métrica de generación")
            self.session.rollback()

    def _check_cancel(self, cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelledError("Generación cancelada por el usuario")

    @staticmethod
    def _report(
        progress: Callable[[str, str], None] | None, stage: str, message: str
    ) -> None:
        if progress is not None:
            progress(stage, message)

    def _retrieve_context(self, *, workspace_id: str, focus: str | None) -> list[ContextRow]:
        if self.embedder is None:
            return get_context_rows(
                self.session,
                workspace_id=workspace_id,
                focus=focus,
                max_chunks=self.settings.semantic_candidate_chunks,
            )
        return ContextRetriever(self.session, self.settings, self.embedder).retrieve(
            workspace_id=workspace_id,
            focus=focus,
        )


def _build_context(rows, *, max_chars: int) -> str:
    parts: list[str] = []
    used = 0
    for row in rows:
        content = sanitize_untrusted_text(row.content)
        if not content:
            continue
        block = f"[Material: {row.filename}]\n{content}\n\n"
        remaining = max_chars - used
        if remaining <= 200:
            break
        if len(block) > remaining:
            block = block[:remaining]
        parts.append(block)
        used += len(block)
        if used >= max_chars:
            break
    return "".join(parts).strip()

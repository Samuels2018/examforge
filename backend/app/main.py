import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    audit,
    auth,
    exams,
    exercises,
    exports,
    health,
    maintenance,
    materials,
    workspaces,
)
from app.core.config import Settings
from app.core.db import Base, create_engine_and_session
from app.core.logging import configure_logging, install_error_handlers, install_middleware
from app.core.migrations import apply_lightweight_migrations
from app.core.security import install_audit_middleware, install_rate_limit
from app.services.background import BackgroundQueue
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.factory import build_embedding_provider
from app.services.generation_cache import GenerationCache
from app.services.llm.base import LLMProvider
from app.services.llm.factory import build_llm_provider

logger = logging.getLogger("examforge")


def create_app(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
) -> FastAPI:
    configure_logging()
    settings = settings or Settings()

    processing_queue = (
        BackgroundQueue(workers=settings.background_workers)
        if settings.background_processing_enabled
        else None
    )
    generation_cache = GenerationCache(
        max_entries=settings.generation_cache_entries,
        ttl_seconds=settings.generation_cache_ttl_seconds,
    )
    engine, session_factory = create_engine_and_session(settings.database_url)
    Base.metadata.create_all(engine)
    apply_lightweight_migrations(engine)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)

    # Un provider por proceso: conserva cachés y secuencias internas (p. ej. offline).
    shared_provider = provider if provider is not None else build_llm_provider(settings)
    shared_embedder = embedder if embedder is not None else build_embedding_provider(settings)
    provider_factory = lambda: shared_provider  # noqa: E731
    embedder_factory = lambda: shared_embedder  # noqa: E731

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info(
            "ExamForge arrancado · provider=%s · db=%s",
            settings.llm_provider,
            settings.database_url,
        )
        if processing_queue is not None:
            processing_queue.start()
        try:
            yield
        finally:
            if processing_queue is not None:
                processing_queue.stop(timeout=settings.background_shutdown_timeout_seconds)
            engine.dispose()
            logger.info("ExamForge detenido")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Convierte material de examen en ejercicios interactivos con feedback razonado.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.processing_queue = processing_queue
    app.state.generation_cache = generation_cache
    app.state.llm_provider_factory = provider_factory
    app.state.embedder_factory = embedder_factory

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_middleware(app)
    install_rate_limit(app, settings)
    install_audit_middleware(app, settings)
    install_error_handlers(app)

    from fastapi import APIRouter

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(audit.router)
    api.include_router(workspaces.router)
    api.include_router(exports.router)
    api.include_router(materials.router)
    api.include_router(maintenance.router)
    api.include_router(exercises.router)
    api.include_router(exams.router)
    app.include_router(api)

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {
            "app": settings.app_name,
            "docs": "/docs",
            "health": "/api/health",
        }

    return app


app = create_app()

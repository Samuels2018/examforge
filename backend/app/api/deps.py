from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AuthError
from app.models import User
from app.services.auth import AuthService
from app.services.embeddings.base import EmbeddingProvider
from app.services.llm.base import LLMProvider

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from app.services.background import BackgroundQueue
    from app.services.generation_cache import GenerationCache
    from app.services.generation_registry import GenerationRegistry


def get_db_session(request: Request) -> Iterator[Session]:
    """Sesión sin scope de usuario. La usan auth y las dependencias internas."""
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def get_current_user(
    request: Request,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    auth = AuthService(session, settings)
    token = _bearer_token(authorization)
    if token:
        user = auth.resolve_token(token)
        if user is None:
            raise AuthError("Sesión caducada o token inválido")
        request.state.auth_token = token
        request.state.user_id = user.id
        return user

    if settings.auth_required:
        raise AuthError("Necesitas iniciar sesión para acceder a este recurso")

    cached = getattr(request.app.state, "default_user", None)
    if cached is None:
        cached = auth.ensure_default_user()
        request.app.state.default_user = cached
    request.state.auth_token = None
    request.state.user_id = cached.id
    return cached


def get_session(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Iterator[Session]:
    """Sesión con aislamiento: los repositorios filtran por owner_id."""
    session.info["owner_id"] = user.id
    yield session


def get_session_factory(request: Request) -> sessionmaker:
    return request.app.state.session_factory


def get_processing_queue(request: Request) -> BackgroundQueue | None:
    return getattr(request.app.state, "processing_queue", None)


def get_generation_cache(request: Request) -> GenerationCache | None:
    return getattr(request.app.state, "generation_cache", None)


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider_factory()


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    return request.app.state.embedder_factory()


def get_generation_registry(request: Request) -> GenerationRegistry:
    from app.services.generation_registry import GenerationRegistry

    registry = getattr(request.app.state, "generation_registry", None)
    if registry is None:
        registry = GenerationRegistry()
        request.app.state.generation_registry = registry
    return registry


def require_workspace(
    workspace_id: str,
    session: Session = Depends(get_session),
) -> str:
    """Valida que el workspace existe y pertenece al usuario de la sesión."""
    from app.services.workspaces import WorkspaceService

    WorkspaceService(session).get_or_404(workspace_id)
    return workspace_id

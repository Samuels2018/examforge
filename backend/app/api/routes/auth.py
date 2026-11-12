from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_session, get_settings
from app.core.config import Settings
from app.core.errors import AuthError
from app.models import User
from app.schemas.auth import (
    AuthStatus,
    LoginRequest,
    RegisterRequest,
    TokenRead,
    UserRead,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatus)
def auth_status(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    authorization: Annotated[str | None, Header()] = None,
) -> AuthStatus:
    auth = AuthService(session, settings)
    token = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
    user = auth.resolve_token(token) if token else None
    if user is None and not settings.auth_required:
        user = auth.ensure_default_user()
    return AuthStatus(
        auth_required=settings.auth_required,
        authenticated=user is not None and not user.is_default,
        user=_user_read(user) if user is not None and not user.is_default else None,
        has_users=auth.has_users(),
    )


@router.post("/register", response_model=TokenRead, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TokenRead:
    user, token, expires_at = AuthService(session, settings).register(
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
    )
    return TokenRead(access_token=token, expires_at=expires_at, user=_user_read(user))


@router.post("/login", response_model=TokenRead)
def login(
    payload: LoginRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TokenRead:
    user, token, expires_at = AuthService(session, settings).login(
        username=payload.username, password=payload.password
    )
    return TokenRead(access_token=token, expires_at=expires_at, user=_user_read(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    _user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    token = getattr(request.state, "auth_token", None)
    if not token:
        raise AuthError("No hay una sesión activa")
    AuthService(session, settings).revoke(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> UserRead:
    return _user_read(user)


def _user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_default=user.is_default,
        created_at=user.created_at,
    )

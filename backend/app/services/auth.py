import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AuthError, ConflictError
from app.models import AuthToken, User, Workspace, new_id

_PBKDF2_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str, *, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_PBKDF2_ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != _PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def register(
        self, *, username: str, password: str, display_name: str | None = None
    ) -> tuple[User, str, datetime]:
        username = username.strip()
        if len(username) < 3 or len(username) > 80:
            raise ConflictError("El usuario debe tener entre 3 y 80 caracteres")
        if username.startswith("__"):
            raise ConflictError("Ese nombre de usuario está reservado")
        if len(password) < 8:
            raise ConflictError("La contraseña debe tener al menos 8 caracteres")
        existing = self.session.scalar(select(User).where(User.username == username))
        if existing is not None:
            raise ConflictError("Ya existe un usuario con ese nombre")

        user = User(
            id=new_id(),
            username=username,
            password_hash=hash_password(
                password, iterations=self.settings.auth_pbkdf2_iterations
            ),
            display_name=(display_name or username).strip()[:120],
        )
        self.session.add(user)
        self.session.flush()
        self._adopt_default_workspaces(user)
        token, expires_at = self._issue_token(user)
        self.session.commit()
        return user, token, expires_at

    def login(self, *, username: str, password: str) -> tuple[User, str, datetime]:
        user = self.session.scalar(select(User).where(User.username == username.strip()))
        if user is None or user.is_default or not verify_password(password, user.password_hash):
            raise AuthError("Usuario o contraseña incorrectos")
        token, expires_at = self._issue_token(user)
        self.session.commit()
        return user, token, expires_at

    def resolve_token(self, token: str) -> User | None:
        if not token:
            return None
        token_hash = hash_token(token)
        row = self.session.scalar(
            select(AuthToken).where(AuthToken.token_hash == token_hash)
        )
        if row is None:
            return None
        expires = _aware(row.expires_at)
        if expires <= datetime.now(UTC):
            self.session.delete(row)
            self.session.commit()
            return None
        user = self.session.get(User, row.user_id)
        if user is None:
            return None
        now = datetime.now(UTC)
        if row.last_used_at is None or _aware(row.last_used_at) < now - timedelta(hours=1):
            row.last_used_at = now
            self.session.commit()
        return user

    def revoke(self, token: str) -> None:
        if not token:
            return
        row = self.session.scalar(
            select(AuthToken).where(AuthToken.token_hash == hash_token(token))
        )
        if row is not None:
            self.session.delete(row)
            self.session.commit()

    def ensure_default_user(self) -> User:
        user = self.session.scalar(
            select(User).where(User.username == self.settings.auth_default_username)
        )
        if user is not None:
            return user
        user = User(
            id=new_id(),
            username=self.settings.auth_default_username,
            password_hash=hash_password(
                secrets.token_urlsafe(32),
                iterations=self.settings.auth_pbkdf2_iterations,
            ),
            display_name="Invitado local",
            is_default=True,
        )
        self.session.add(user)
        self.session.flush()
        self._adopt_default_workspaces(user)
        self.session.commit()
        return user

    def has_users(self) -> bool:
        return (
            self.session.scalar(
                select(User.id).where(User.is_default.is_(False)).limit(1)
            )
            is not None
        )

    def _issue_token(self, user: User) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(40)
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.auth_token_days)
        self.session.add(
            AuthToken(
                id=new_id(),
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=expires_at,
            )
        )
        return token, expires_at

    def _adopt_default_workspaces(self, user: User) -> None:
        """Traslada los datos anónimos al primer usuario real.

        Si el usuario que se acaba de crear es el primero no-default, los
        workspaces sin dueño (o del usuario implícito) pasan a ser suyos.
        """
        real_users = self.session.scalar(
            select(User.id).where(User.is_default.is_(False), User.id != user.id).limit(1)
        )
        if real_users is not None:
            return
        default_user = self.session.scalar(
            select(User).where(User.is_default.is_(True), User.id != user.id)
        )
        owner_ids = [user.id]
        if default_user is not None:
            owner_ids.append(default_user.id)
        self.session.execute(
            update(Workspace)
            .where(Workspace.owner_id.is_(None) | Workspace.owner_id.in_(owner_ids))
            .values(owner_id=user.id)
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

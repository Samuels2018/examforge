import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, new_id

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class AuditService:
    """Persistencia y consulta de la auditoría local."""

    def __init__(self, session_factory: SessionFactory, *, max_events: int = 5_000) -> None:
        self.session_factory = session_factory
        self.max_events = max(100, max_events)

    def record(
        self,
        *,
        user_id: str | None,
        method: str,
        path: str,
        status_code: int,
        duration_ms: int = 0,
        client_ip: str | None = None,
        request_id: str | None = None,
    ) -> None:
        session = self.session_factory()
        try:
            session.add(
                AuditLog(
                    id=new_id(),
                    user_id=user_id,
                    action=f"{method.upper()} {path}"[:60],
                    method=method.upper()[:10],
                    path=path[:300],
                    status_code=status_code,
                    duration_ms=max(0, duration_ms),
                    client_ip=(client_ip or "")[:64] or None,
                    request_id=(request_id or "")[:64] or None,
                )
            )
            session.commit()
            cleanup_old_events(session, keep=self.max_events)
        except Exception:
            session.rollback()
            logger.exception("No se pudo registrar el evento de auditoría")
        finally:
            session.close()


def list_events(
    session: Session,
    *,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id)
    if user_id is not None:
        statement = statement.where(AuditLog.user_id == user_id)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def cleanup_old_events(session: Session, *, keep: int) -> int:
    """Mantiene como máximo `keep` eventos; devuelve cuántos borró."""
    stale_ids = session.scalars(
        select(AuditLog.id).order_by(AuditLog.created_at.desc()).offset(max(0, keep))
    ).all()
    removed = 0
    for event_id in stale_ids:
        event = session.get(AuditLog, event_id)
        if event is not None:
            session.delete(event)
            removed += 1
    if removed:
        session.commit()
    return removed

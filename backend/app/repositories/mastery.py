from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AttemptDiagnostic, TopicMastery


def list_mastery(session: Session, workspace_id: str) -> list[TopicMastery]:
    return list(
        session.scalars(
            select(TopicMastery)
            .where(TopicMastery.workspace_id == workspace_id)
            .order_by(TopicMastery.mastery.asc(), TopicMastery.due_at.asc())
        )
    )


def mastery_for_topics(
    session: Session, *, workspace_id: str, topic_keys: list[str]
) -> dict[str, TopicMastery]:
    if not topic_keys:
        return {}
    rows = session.scalars(
        select(TopicMastery).where(
            TopicMastery.workspace_id == workspace_id,
            TopicMastery.topic_key.in_(topic_keys),
        )
    )
    return {row.topic_key: row for row in rows}


@dataclass(frozen=True)
class ErrorPatternRow:
    topic: str
    error_type: str
    count: int
    detail: str
    last_seen_at: datetime


def list_error_patterns(
    session: Session, *, workspace_id: str, min_count: int = 1
) -> list[ErrorPatternRow]:
    counts = session.execute(
        select(
            AttemptDiagnostic.topic,
            AttemptDiagnostic.error_type,
            func.count(AttemptDiagnostic.id),
            func.max(AttemptDiagnostic.created_at),
        )
        .where(AttemptDiagnostic.workspace_id == workspace_id)
        .group_by(AttemptDiagnostic.topic, AttemptDiagnostic.error_type)
        .having(func.count(AttemptDiagnostic.id) >= min_count)
    ).all()
    if not counts:
        return []

    # Una sola consulta extra para recuperar el detalle más reciente por patrón.
    details = session.execute(
        select(
            AttemptDiagnostic.topic,
            AttemptDiagnostic.error_type,
            AttemptDiagnostic.detail,
        )
        .where(AttemptDiagnostic.workspace_id == workspace_id)
        .order_by(AttemptDiagnostic.created_at.desc(), AttemptDiagnostic.id)
    ).all()
    latest: dict[tuple[str, str], str] = {}
    for topic, error_type, detail in details:
        latest.setdefault((topic, error_type), detail)
    return sorted(
        [
            ErrorPatternRow(
                topic=topic,
                error_type=error_type,
                count=int(count),
                detail=latest.get((topic, error_type), ""),
                last_seen_at=last_seen,
            )
            for topic, error_type, count, last_seen in counts
        ],
        key=lambda row: (row.count, row.last_seen_at),
        reverse=True,
    )

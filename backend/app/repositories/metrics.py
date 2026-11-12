from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import GenerationMetric


def list_generation_metrics(
    session: Session, *, workspace_id: str, limit: int
) -> list[GenerationMetric]:
    return list(
        session.scalars(
            select(GenerationMetric)
            .where(GenerationMetric.workspace_id == workspace_id)
            .order_by(GenerationMetric.created_at.desc(), GenerationMetric.id)
            .limit(limit)
        )
    )


def generation_metrics_summary(session: Session, *, workspace_id: str) -> tuple[int, int, int, int]:
    row = session.execute(
        select(
            func.count(GenerationMetric.id),
            func.coalesce(
                func.sum(case((GenerationMetric.cached.is_(True), 1), else_=0)), 0
            ),
            func.coalesce(func.avg(GenerationMetric.duration_ms), 0),
            func.coalesce(func.sum(GenerationMetric.total_tokens), 0),
        ).where(GenerationMetric.workspace_id == workspace_id)
    ).one()
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])

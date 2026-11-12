from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Attempt, Exercise, Material, Workspace
from app.schemas.workspace import WorkspaceSummary


@dataclass(frozen=True)
class WorkspaceUsage:
    material_count: int
    storage_bytes: int
    exercise_count: int


def workspace_usage(session: Session, workspace_id: str) -> WorkspaceUsage:
    material_count = (
        session.scalar(
            select(func.count(Material.id)).where(Material.workspace_id == workspace_id)
        )
        or 0
    )
    storage_bytes = (
        session.scalar(
            select(func.coalesce(func.sum(Material.size_bytes), 0)).where(
                Material.workspace_id == workspace_id
            )
        )
        or 0
    )
    exercise_count = (
        session.scalar(
            select(func.count(Exercise.id)).where(Exercise.workspace_id == workspace_id)
        )
        or 0
    )
    return WorkspaceUsage(
        material_count=int(material_count),
        storage_bytes=int(storage_bytes),
        exercise_count=int(exercise_count),
    )


def owner_scope(session: Session) -> str | None:
    """Devuelve el owner activo de la sesión, si la petición está autenticada."""
    return session.info.get("owner_id")


def get_workspace(session: Session, workspace_id: str) -> Workspace | None:
    workspace = session.get(Workspace, workspace_id)
    owner_id = owner_scope(session)
    if workspace is None or (owner_id is not None and workspace.owner_id != owner_id):
        return None
    return workspace


def list_workspace_summaries(
    session: Session, *, limit: int, offset: int
) -> tuple[list[WorkspaceSummary], int]:
    owner_id = owner_scope(session)
    total_query = select(func.count(Workspace.id))
    list_query = select(Workspace)
    if owner_id is not None:
        total_query = total_query.where(Workspace.owner_id == owner_id)
        list_query = list_query.where(Workspace.owner_id == owner_id)
    total = session.scalar(total_query) or 0
    workspaces = session.scalars(
        list_query.order_by(Workspace.updated_at.desc(), Workspace.id).limit(limit).offset(offset)
    ).all()
    if not workspaces:
        return [], total

    workspace_ids = [workspace.id for workspace in workspaces]

    material_counts = dict(
        session.execute(
            select(Material.workspace_id, func.count(Material.id))
            .where(Material.workspace_id.in_(workspace_ids))
            .group_by(Material.workspace_id)
        ).all()
    )
    exercise_counts = dict(
        session.execute(
            select(Exercise.workspace_id, func.count(Exercise.id))
            .where(Exercise.workspace_id.in_(workspace_ids))
            .group_by(Exercise.workspace_id)
        ).all()
    )
    attempt_stats = {
        workspace_id: (int(attempts or 0), int(correct or 0))
        for workspace_id, attempts, correct in session.execute(
            select(
                Attempt.workspace_id,
                func.count(Attempt.id),
                func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)),
            )
            .where(Attempt.workspace_id.in_(workspace_ids))
            .group_by(Attempt.workspace_id)
        ).all()
    }

    summaries = []
    for workspace in workspaces:
        attempts, correct = attempt_stats.get(workspace.id, (0, 0))
        summaries.append(
            WorkspaceSummary(
                id=workspace.id,
                name=workspace.name,
                description=workspace.description,
                exam_date=workspace.exam_date,
                created_at=workspace.created_at,
                updated_at=workspace.updated_at,
                material_count=int(material_counts.get(workspace.id, 0)),
                exercise_count=int(exercise_counts.get(workspace.id, 0)),
                attempt_count=attempts,
                correct_attempt_count=correct,
                accuracy=round(correct / attempts, 3) if attempts else 0.0,
            )
        )
    return summaries, total

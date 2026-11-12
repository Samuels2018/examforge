from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Workspace
from app.repositories.workspaces import get_workspace, list_workspace_summaries, owner_scope
from app.schemas.workspace import WorkspaceCreate, WorkspaceSummary, WorkspaceUpdate


class WorkspaceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: WorkspaceCreate) -> Workspace:
        workspace = Workspace(
            name=payload.name,
            description=payload.description.strip(),
            exam_date=payload.exam_date,
            owner_id=owner_scope(self.session),
        )
        self.session.add(workspace)
        self.session.commit()
        self.session.refresh(workspace)
        return workspace

    def list(self, *, limit: int, offset: int) -> tuple[list[WorkspaceSummary], int]:
        return list_workspace_summaries(self.session, limit=limit, offset=offset)

    def get_or_404(self, workspace_id: str) -> Workspace:
        workspace = get_workspace(self.session, workspace_id)
        if workspace is None:
            raise NotFoundError("Evaluación no encontrada")
        return workspace

    def update(self, workspace_id: str, payload: WorkspaceUpdate) -> Workspace:
        workspace = self.get_or_404(workspace_id)
        changes = payload.model_dump(exclude_unset=True)
        if "description" in changes and changes["description"] is not None:
            changes["description"] = changes["description"].strip()
        for field, value in changes.items():
            setattr(workspace, field, value)
        self.session.commit()
        self.session.refresh(workspace)
        return workspace

    def delete(self, workspace_id: str) -> None:
        workspace = self.get_or_404(workspace_id)
        self.session.delete(workspace)
        self.session.commit()

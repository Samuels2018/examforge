from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.mastery import ErrorPattern, MasteryOverview
from app.schemas.progress import ProgressRead, StudyPlan
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceRead,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from app.services.diagnostics import DiagnosticService
from app.services.mastery import MasteryService
from app.services.progress import ProgressService
from app.services.workspaces import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceSummary])
def list_workspaces(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
) -> list[WorkspaceSummary]:
    items, _total = WorkspaceService(session).list(limit=limit, offset=offset)
    return items


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    session: Session = Depends(get_session),
) -> WorkspaceRead:
    workspace = WorkspaceService(session).create(payload)
    return WorkspaceRead.model_validate(workspace)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace_detail(
    workspace_id: str,
    session: Session = Depends(get_session),
) -> WorkspaceRead:
    workspace = WorkspaceService(session).get_or_404(workspace_id)
    return WorkspaceRead.model_validate(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    session: Session = Depends(get_session),
) -> WorkspaceRead:
    workspace = WorkspaceService(session).update(workspace_id, payload)
    return WorkspaceRead.model_validate(workspace)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: str,
    session: Session = Depends(get_session),
) -> Response:
    WorkspaceService(session).delete(workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/progress", response_model=ProgressRead)
def get_progress(
    workspace_id: str,
    session: Session = Depends(get_session),
) -> ProgressRead:
    return ProgressService(session).get_progress(workspace_id)


@router.get("/{workspace_id}/study-plan", response_model=StudyPlan)
def get_study_plan(
    workspace_id: str,
    session: Session = Depends(get_session),
) -> StudyPlan:
    return ProgressService(session).get_study_plan(workspace_id)


@router.get("/{workspace_id}/mastery", response_model=MasteryOverview)
def get_mastery(
    workspace_id: str,
    session: Session = Depends(get_session),
) -> MasteryOverview:
    WorkspaceService(session).get_or_404(workspace_id)
    return MasteryService(session).overview(workspace_id)


@router.get("/{workspace_id}/diagnostics", response_model=list[ErrorPattern])
def get_diagnostics(
    workspace_id: str,
    session: Session = Depends(get_session),
) -> list[ErrorPattern]:
    WorkspaceService(session).get_or_404(workspace_id)
    return DiagnosticService(session).patterns(workspace_id)

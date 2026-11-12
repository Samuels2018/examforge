from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_llm_provider, get_session, get_settings, require_workspace
from app.core.config import Settings
from app.schemas.exam import ExamRead, ExamResult, ExamStartRequest, ExamSubmitRequest
from app.services.exams import ExamService
from app.services.llm.base import LLMProvider

router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams",
    tags=["exams"],
    dependencies=[Depends(require_workspace)],
)


@router.post("", response_model=ExamRead, status_code=status.HTTP_201_CREATED)
def start_exam(
    workspace_id: str,
    payload: ExamStartRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExamRead:
    return ExamService(session, settings, provider).create(workspace_id, payload)


@router.get("/{exam_id}", response_model=ExamRead)
def get_exam(
    workspace_id: str,
    exam_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExamRead:
    return ExamService(session, settings, provider).get(workspace_id, exam_id)


@router.post("/{exam_id}/submit", response_model=ExamResult)
def submit_exam(
    workspace_id: str,
    exam_id: str,
    payload: ExamSubmitRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExamResult:
    return ExamService(session, settings, provider).submit(workspace_id, exam_id, payload)

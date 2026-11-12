from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.audit import AuditEventRead
from app.services.audit import list_events

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventRead])
def list_audit_events(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
) -> list[AuditEventRead]:
    owner_id = session.info.get("owner_id")
    events = list_events(session, user_id=owner_id, limit=limit, offset=offset)
    return [AuditEventRead.model_validate(event) for event in events]

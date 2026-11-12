from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.services.exporting import ExportService

router = APIRouter(prefix="/workspaces/{workspace_id}/export", tags=["exports"])


@router.get("")
def export_workspace(
    workspace_id: str,
    export_format: Annotated[
        Literal["markdown", "json", "pdf"], Query(alias="format")
    ] = "markdown",
    session: Session = Depends(get_session),
) -> Response:
    result = ExportService(session).export(workspace_id, export_format)
    disposition = (
        f"attachment; filename=\"{result.filename}\"; "
        f"filename*=UTF-8''{quote(result.filename)}"
    )
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": disposition},
    )

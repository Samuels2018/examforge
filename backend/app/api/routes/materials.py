from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_processing_queue, get_session, get_session_factory, get_settings
from app.core.config import Settings
from app.core.errors import FileTooLargeError, TooManyFilesError
from app.schemas.common import Page
from app.schemas.material import ImportRequest, MaterialDetail, MaterialRead
from app.services.background import BackgroundQueue
from app.services.importing import ImportService
from app.services.ingestion import IncomingFile, MaterialService

router = APIRouter(prefix="/workspaces/{workspace_id}/materials", tags=["materials"])


@router.get("", response_model=Page[MaterialRead])
def list_materials(
    workspace_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Page[MaterialRead]:
    items, total = MaterialService(session, settings).list(
        workspace_id, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=list[MaterialRead], status_code=status.HTTP_201_CREATED)
def upload_materials(
    workspace_id: str,
    files: Annotated[list[UploadFile], File(description="Archivos del examen")],
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    queue: BackgroundQueue | None = Depends(get_processing_queue),
    session_factory=Depends(get_session_factory),
) -> list[MaterialRead]:
    if len(files) > settings.max_files_per_upload:
        raise TooManyFilesError(
            f"Puedes subir como máximo {settings.max_files_per_upload} archivos por petición"
        )
    incoming = []
    for upload in files:
        data = upload.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise FileTooLargeError(
                f"{upload.filename} supera el límite de {settings.max_upload_mb} MB"
            )
        incoming.append(
            IncomingFile(
                filename=upload.filename or "archivo",
                content_type=upload.content_type or "",
                data=data,
            )
        )
    return MaterialService(
        session, settings, queue=queue, session_factory=session_factory
    ).add_files(workspace_id, incoming)


@router.post("/import", response_model=list[MaterialRead], status_code=status.HTTP_201_CREATED)
def import_material(
    workspace_id: str,
    payload: ImportRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    queue: BackgroundQueue | None = Depends(get_processing_queue),
    session_factory=Depends(get_session_factory),
) -> list[MaterialRead]:
    return ImportService(
        session, settings, queue=queue, session_factory=session_factory
    ).import_url(workspace_id, payload.url)


@router.get("/{material_id}", response_model=MaterialDetail)
def get_material(
    workspace_id: str,
    material_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MaterialDetail:
    return MaterialService(session, settings).get_detail(workspace_id, material_id)


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    workspace_id: str,
    material_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    MaterialService(session, settings).delete(workspace_id, material_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

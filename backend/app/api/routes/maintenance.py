from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_current_user, get_settings
from app.core.config import Settings
from app.models import User
from app.schemas.maintenance import BackupRead, RestoreRequest
from app.services.backup import BackupInfo, BackupService

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


def _read(info: BackupInfo) -> BackupRead:
    return BackupRead(
        filename=info.filename,
        size_bytes=info.size_bytes,
        created_at=info.created_at,
    )


@router.get("/backups", response_model=list[BackupRead])
def list_backups(
    settings: Settings = Depends(get_settings),
    _user: User = Depends(get_current_user),
) -> list[BackupRead]:
    return [_read(info) for info in BackupService(settings).list()]


@router.post("/backup", response_model=BackupRead, status_code=status.HTTP_201_CREATED)
def create_backup(
    settings: Settings = Depends(get_settings),
    _user: User = Depends(get_current_user),
) -> BackupRead:
    return _read(BackupService(settings).create())


@router.post("/restore", response_model=BackupRead)
def restore_backup(
    payload: RestoreRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    _user: User = Depends(get_current_user),
) -> BackupRead:
    info = BackupService(settings).restore(
        payload.filename,
        engine=getattr(request.app.state, "engine", None),
    )
    return _read(info)

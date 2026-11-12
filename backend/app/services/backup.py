import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupInfo:
    filename: str
    path: Path
    size_bytes: int
    created_at: datetime


class BackupService:
    """Copias consistentes de SQLite usando la API de backup del motor."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create(self) -> BackupInfo:
        source = self._database_path()
        if source is None:
            raise AppError(
                "El backup integrado solo está disponible con SQLite. "
                "Para Postgres usa pg_dump."
            )
        if not source.exists():
            raise NotFoundError("La base de datos todavía no existe")

        self._backup_dir().mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self._backup_dir() / f"examforge-{timestamp}.db"
        self._copy_database(source, destination)
        self._trim()
        info = self._info(destination)
        logger.info("Backup creado: %s (%s bytes)", info.filename, info.size_bytes)
        return info

    def list(self) -> list[BackupInfo]:
        directory = self._backup_dir()
        if not directory.exists():
            return []
        files = sorted(directory.glob("examforge-*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
        return [self._info(path) for path in files if path.is_file()]

    def restore(self, filename: str, *, engine: Engine | None = None) -> BackupInfo:
        source = self._resolve_backup(filename)
        current = self._database_path()
        if current is None:
            raise AppError(
                "El restore integrado solo está disponible con SQLite. "
                "Para Postgres restaura con pg_restore."
            )

        # Guarda una copia de seguridad del estado actual antes de sobrescribir.
        if current.exists():
            safety = self._backup_dir() / (
                f"examforge-pre-restore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.db"
            )
            self._copy_database(current, safety)
            logger.info("Copia previa al restore: %s", safety.name)

        if engine is not None:
            engine.dispose()
        self._copy_database(source, current)
        info = self._info(source)
        logger.warning("Base de datos restaurada desde %s", info.filename)
        return info

    def _resolve_backup(self, filename: str) -> Path:
        name = Path(filename).name
        if name != filename or not name.startswith("examforge-") or not name.endswith(".db"):
            raise AppError("Nombre de backup inválido")
        path = self._backup_dir() / name
        if not path.is_file():
            raise NotFoundError("Backup no encontrado")
        return path

    def _trim(self) -> None:
        backups = self.list()
        for stale in backups[self.settings.backup_max_files :]:
            stale.path.unlink(missing_ok=True)

    def _info(self, path: Path) -> BackupInfo:
        stat = path.stat()
        return BackupInfo(
            filename=path.name,
            path=path,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )

    def _backup_dir(self) -> Path:
        return self.settings.backup_dir

    def _database_path(self) -> Path | None:
        url = make_url(self.settings.database_url)
        if not url.drivername.startswith("sqlite"):
            return None
        if not url.database or url.database == ":memory:":
            return None
        return Path(url.database).expanduser()

    @staticmethod
    def _copy_database(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_connection = sqlite3.connect(source)
        try:
            destination_connection = sqlite3.connect(destination)
            try:
                source_connection.backup(destination_connection)
            finally:
                destination_connection.close()
        finally:
            source_connection.close()

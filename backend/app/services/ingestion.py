import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    FileTooLargeError,
    InvalidMaterialError,
    NotFoundError,
    QuotaExceededError,
    UnsupportedFileError,
)
from app.models import Material, MaterialChunk, new_id
from app.models.enums import MaterialStatus
from app.repositories.materials import (
    MaterialWithCount,
    count_chunks_for_material,
    get_material,
    list_materials_with_counts,
)
from app.repositories.workspaces import get_workspace, workspace_usage
from app.schemas.material import MaterialDetail, MaterialRead
from app.services.background import BackgroundQueue, process_material_job
from app.services.parsing import SUPPORTED_EXTENSIONS, chunk_text, extract_text

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class IncomingFile:
    filename: str
    content_type: str
    data: bytes


class MaterialService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        queue: BackgroundQueue | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.queue = queue
        self.session_factory = session_factory

    def add_files(self, workspace_id: str, files: list[IncomingFile]) -> list[MaterialRead]:
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")
        if not files:
            raise UnsupportedFileError("No se recibió ningún archivo")

        for incoming in files:
            self._validate(incoming)
        self._enforce_quota(workspace_id, files)

        workspace_dir = self.settings.upload_dir / workspace_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        created: list[MaterialWithCount] = []
        pending: list[Material] = []
        for incoming in files:
            safe_name = _safe_filename(incoming.filename)
            destination = workspace_dir / f"{uuid4().hex}_{safe_name}"
            destination.write_bytes(incoming.data)

            material = Material(
                id=new_id(),
                workspace_id=workspace_id,
                filename=incoming.filename[:255],
                stored_path=str(destination),
                content_type=incoming.content_type or "",
                size_bytes=len(incoming.data),
                status=MaterialStatus.PROCESSING.value,
            )
            self.session.add(material)
            self.session.flush()

            if self._should_process_in_background(len(incoming.data)):
                pending.append(material)
                chunk_count = 0
            else:
                chunk_count = self.process_material(material, commit=False)

            created.append(MaterialWithCount(material=material, chunk_count=chunk_count))

        self.session.commit()

        queue = self.queue
        session_factory = self.session_factory
        for material in pending:
            if queue is None or session_factory is None:
                self.process_material(material)
                continue

            def job(material_id: str = material.id) -> None:
                process_material_job(session_factory, self.settings, material_id)

            try:
                queue.submit(job)
            except RuntimeError:
                logger.warning("Cola no disponible; procesando material inline")
                self.process_material(material)
        if pending:
            self.session.commit()

        return [
            _material_read(item.material, chunk_count=item.chunk_count) for item in created
        ]

    def process_material(self, material: Material, *, commit: bool = True) -> int:
        """Extrae texto y crea chunks. Nunca propaga errores de parseo."""
        material_id = material.id
        try:
            text = extract_text(
                Path(material.stored_path),
                max_chars=self.settings.max_extracted_chars,
                ocr_language=self.settings.ocr_language,
                ocr_enabled=self.settings.ocr_enabled,
                sample_rows=self.settings.tabular_sample_rows,
            )
            chunks = chunk_text(
                text,
                max_chars=self.settings.chunk_max_chars,
                overlap=self.settings.chunk_overlap_chars,
            )
            if not chunks:
                raise ValueError("El archivo no produjo fragmentos de texto")
            self.session.add_all(
                [
                    MaterialChunk(
                        material_id=material.id,
                        workspace_id=material.workspace_id,
                        idx=index,
                        content=content,
                        char_count=len(content),
                    )
                    for index, content in enumerate(chunks)
                ]
            )
            material.extracted_text = text
            material.char_count = len(text)
            material.status = MaterialStatus.READY.value
            material.error_message = None
            chunk_count = len(chunks)
        except Exception as exc:  # el fallo de un archivo no debe tumbar el lote
            logger.warning("No se pudo procesar %s: %s", material.filename, exc)
            self.session.rollback()
            current = self.session.get(Material, material_id)
            if current is not None:
                current.status = MaterialStatus.FAILED.value
                current.error_message = str(exc)[:1_000]
                current.extracted_text = ""
                current.char_count = 0
            chunk_count = 0

        if commit:
            self.session.commit()
        return chunk_count

    def _should_process_in_background(self, size_bytes: int) -> bool:
        return (
            self.settings.background_processing_enabled
            and self.queue is not None
            and self.queue.started
            and self.session_factory is not None
            and size_bytes >= self.settings.background_processing_threshold_bytes
        )

    def _enforce_quota(self, workspace_id: str, files: list[IncomingFile]) -> None:
        usage = workspace_usage(self.session, workspace_id)
        if usage.material_count + len(files) > self.settings.workspace_max_materials:
            raise QuotaExceededError(
                "Has alcanzado el límite de materiales de esta evaluación. "
                "Borra algún material antes de subir más."
            )
        incoming_bytes = sum(len(incoming.data) for incoming in files)
        if usage.storage_bytes + incoming_bytes > self.settings.workspace_max_storage_bytes:
            raise QuotaExceededError(
                f"La evaluación supera el límite de almacenamiento de "
                f"{self.settings.workspace_max_storage_mb} MB."
            )

    def list(
        self, workspace_id: str, *, limit: int, offset: int
    ) -> tuple[list[MaterialRead], int]:
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")
        items, total = list_materials_with_counts(
            self.session, workspace_id=workspace_id, limit=limit, offset=offset
        )
        return [
            _material_read(item.material, chunk_count=item.chunk_count) for item in items
        ], total

    def get_detail(self, workspace_id: str, material_id: str) -> MaterialDetail:
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")
        material = get_material(self.session, workspace_id, material_id)
        if material is None:
            raise NotFoundError("Material no encontrado")
        chunk_count = count_chunks_for_material(self.session, material.id)
        return MaterialDetail(
            **_material_read(material, chunk_count=chunk_count).model_dump(),
            preview=material.extracted_text[:500],
        )

    def delete(self, workspace_id: str, material_id: str) -> None:
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")
        material = get_material(self.session, workspace_id, material_id)
        if material is None:
            raise NotFoundError("Material no encontrado")
        Path(material.stored_path).unlink(missing_ok=True)
        self.session.delete(material)
        self.session.commit()

    def _validate(self, incoming: IncomingFile) -> None:
        if len(incoming.data) > self.settings.max_upload_bytes:
            raise FileTooLargeError(
                f"{incoming.filename} supera el límite de {self.settings.max_upload_mb} MB"
            )
        suffix = Path(incoming.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFileError(
                f"Formato no soportado: {suffix or 'sin extensión'}. "
                f"Formatos válidos: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        if not incoming.data:
            raise InvalidMaterialError(f"{incoming.filename} está vacío")


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    cleaned = _SAFE_NAME.sub("_", name).strip("._") or "archivo"
    return cleaned[:150]


def _material_read(material: Material, *, chunk_count: int) -> MaterialRead:
    return MaterialRead(
        id=material.id,
        workspace_id=material.workspace_id,
        filename=material.filename,
        content_type=material.content_type,
        size_bytes=material.size_bytes,
        status=MaterialStatus(material.status),
        char_count=material.char_count,
        chunk_count=chunk_count,
        error_message=material.error_message,
        created_at=material.created_at,
    )

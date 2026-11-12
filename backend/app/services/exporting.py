import json
import textwrap
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.core.errors import NotFoundError
from app.models import Attempt, Exercise, Material, MaterialChunk
from app.repositories.progress import overall_stats
from app.repositories.workspaces import get_workspace
from app.services.progress import ProgressService

ExportFormat = Literal["markdown", "json", "pdf"]

_MEDIA_TYPES = {
    "markdown": "text/markdown; charset=utf-8",
    "json": "application/json",
    "pdf": "application/pdf",
}
_EXTENSIONS = {"markdown": "md", "json": "json", "pdf": "pdf"}


@dataclass(frozen=True)
class ExportResult:
    content: bytes
    media_type: str
    filename: str


class ExportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def export(self, workspace_id: str, export_format: ExportFormat) -> ExportResult:
        workspace = get_workspace(self.session, workspace_id)
        if workspace is None:
            raise NotFoundError("Evaluación no encontrada")
        payload = self._payload(workspace)
        if export_format == "json":
            content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        elif export_format == "markdown":
            content = _to_markdown(payload).encode("utf-8")
        else:
            content = _to_pdf(payload)
        stem = _safe_stem(workspace.name) or "evaluacion"
        filename = f"{stem}-{date.today().isoformat()}.{_EXTENSIONS[export_format]}"
        return ExportResult(content, _MEDIA_TYPES[export_format], filename)

    def _payload(self, workspace) -> dict:
        materials = self.session.execute(
            select(Material, func.count(MaterialChunk.id))
            .outerjoin(MaterialChunk, MaterialChunk.material_id == Material.id)
            .where(Material.workspace_id == workspace.id)
            .options(defer(Material.extracted_text))
            .group_by(Material.id)
            .order_by(Material.created_at, Material.id)
        ).all()
        exercises = self.session.scalars(
            select(Exercise)
            .where(Exercise.workspace_id == workspace.id)
            .order_by(Exercise.created_at, Exercise.id)
        ).all()
        attempts = self.session.execute(
            select(
                Attempt.id,
                Attempt.exercise_id,
                Exercise.question,
                Exercise.topic,
                Attempt.answer,
                Attempt.is_correct,
                Attempt.score,
                Attempt.feedback,
                Attempt.created_at,
            )
            .join(Exercise, Attempt.exercise_id == Exercise.id)
            .where(Attempt.workspace_id == workspace.id)
            .order_by(Attempt.created_at, Attempt.id)
            .limit(5_000)
        ).all()
        stats = overall_stats(self.session, workspace.id)
        plan = ProgressService(self.session).get_study_plan(workspace.id)
        return {
            "workspace": {
                "id": workspace.id,
                "name": workspace.name,
                "description": workspace.description,
                "exam_date": _iso(workspace.exam_date),
                "created_at": _iso(workspace.created_at),
            },
            "summary": {
                "materials": len(materials),
                "exercises": stats.total_exercises,
                "attempts": stats.attempts,
                "correct": stats.correct,
                "accuracy": round(stats.correct / stats.attempts * 100, 1)
                if stats.attempts
                else 0.0,
            },
            "materials": [
                {
                    "id": material.id,
                    "filename": material.filename,
                    "status": material.status,
                    "char_count": material.char_count,
                    "chunk_count": int(chunk_count),
                }
                for material, chunk_count in materials
            ],
            "exercises": [
                {
                    "id": exercise.id,
                    "topic": exercise.topic,
                    "difficulty": exercise.difficulty,
                    "kind": exercise.kind,
                    "question": exercise.question,
                    "options": exercise.options or [],
                    "correct_answer": exercise.correct_answer,
                    "explanation": exercise.explanation,
                    "hint": exercise.hint,
                    "created_at": _iso(exercise.created_at),
                }
                for exercise in exercises
            ],
            "study_plan": {
                "summary": plan.summary,
                "steps": [step.model_dump() for step in plan.steps],
            },
            "attempts": [
                {
                    "id": row[0],
                    "exercise_id": row[1],
                    "question": row[2],
                    "topic": row[3],
                    "answer": row[4],
                    "is_correct": row[5],
                    "score": row[6],
                    "feedback": row[7],
                    "created_at": _iso(row[8]),
                }
                for row in attempts
            ],
        }


def _to_markdown(payload: dict) -> str:
    workspace = payload["workspace"]
    summary = payload["summary"]
    lines = [
        f"# {workspace['name']}",
        "",
        workspace["description"] or "_Sin descripción_",
        "",
        f"- Fecha de examen: {workspace['exam_date'] or 'sin definir'}",
        f"- Materiales: {summary['materials']}",
        f"- Ejercicios: {summary['exercises']}",
        f"- Intentos: {summary['attempts']} · Aciertos: {summary['correct']} "
        f"({summary['accuracy']}%)",
        "",
        "## Materiales",
        "",
    ]
    if not payload["materials"]:
        lines.append("_Sin materiales_")
    for material in payload["materials"]:
        lines.append(
            f"- **{material['filename']}** · {material['status']} · "
            f"{material['char_count']} caracteres · {material['chunk_count']} fragmentos"
        )
    lines.extend(["", "## Plan de ataque", "", payload["study_plan"]["summary"], ""])
    for index, step in enumerate(payload["study_plan"]["steps"], start=1):
        lines.append(f"{index}. **{step['title']}** · {step['reason']}")
        lines.append(f"   - Acción: {step['action']}")
    lines.extend(["", "## Ejercicios", ""])
    if not payload["exercises"]:
        lines.append("_Sin ejercicios_")
    for index, exercise in enumerate(payload["exercises"], start=1):
        lines.append(
            f"### {index}. [{exercise['difficulty']}] {exercise['topic']} "
            f"({exercise['kind']})"
        )
        lines.extend(["", exercise["question"], ""])
        for option in exercise["options"]:
            label = option.get("label") or option.get("id") or ""
            text = option.get("text") or option.get("value") or ""
            lines.append(f"- **{label}.** {text}")
        if exercise["options"]:
            lines.append("")
        lines.append(f"**Respuesta:** {exercise['correct_answer']}")
        if exercise["explanation"]:
            lines.extend(["", f"**Explicación:** {exercise['explanation']}"])
        lines.append("")
    lines.extend(["## Intentos", ""])
    if not payload["attempts"]:
        lines.append("_Sin intentos registrados_")
    for attempt in payload["attempts"]:
        mark = "correcto" if attempt["is_correct"] else "incorrecto"
        lines.append(
            f"- {attempt['created_at']} · {attempt['topic']} · {mark} · "
            f"puntuación {attempt['score']}"
        )
    return "\n".join(lines).strip() + "\n"


def _to_pdf(payload: dict) -> bytes:
    workspace = payload["workspace"]
    summary = payload["summary"]
    text_lines: list[str] = [workspace["name"], ""]
    if workspace["description"]:
        text_lines.extend(_wrap(workspace["description"]))
    text_lines.extend(
        [
            "",
            f"Fecha de examen: {workspace['exam_date'] or 'sin definir'}",
            f"Materiales: {summary['materials']} · Ejercicios: {summary['exercises']}",
            f"Intentos: {summary['attempts']} · Aciertos: {summary['correct']} "
            f"({summary['accuracy']}%)",
            "",
            "MATERIALES",
        ]
    )
    for material in payload["materials"]:
        text_lines.extend(
            _wrap(
                f"- {material['filename']} · {material['status']} · "
                f"{material['char_count']} caracteres"
            )
        )
    text_lines.extend(["", "PLAN DE ATAQUE"])
    text_lines.extend(_wrap(payload["study_plan"]["summary"]))
    for index, step in enumerate(payload["study_plan"]["steps"], start=1):
        text_lines.extend(
            _wrap(f"{index}. {step['title']} · {step['reason']} Acción: {step['action']}")
        )
    text_lines.extend(["", "EJERCICIOS"])
    for index, exercise in enumerate(payload["exercises"], start=1):
        text_lines.extend(
            _wrap(
                f"{index}. [{exercise['difficulty']}] {exercise['topic']}: "
                f"{exercise['question']}"
            )
        )
        for option in exercise["options"]:
            label = option.get("label") or option.get("id") or ""
            text = option.get("text") or option.get("value") or ""
            text_lines.extend(_wrap(f"   {label}. {text}"))
        text_lines.extend(_wrap(f"   Respuesta: {exercise['correct_answer']}"))
        if exercise["explanation"]:
            text_lines.extend(_wrap(f"   Explicación: {exercise['explanation']}"))
        text_lines.append("")
    return _build_pdf(text_lines)


def _wrap(text: str, width: int = 92) -> list[str]:
    if not text:
        return [""]
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, width=width) or [""])
    return lines


def _build_pdf(lines: list[str]) -> bytes:
    lines_per_page = 52
    pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [
        [""]
    ]
    objects: list[bytes] = []

    def add_object(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog_id = add_object(b"")
    pages_id = add_object(b"")
    font_id = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    page_ids = []
    for page_lines in pages:
        content = ["BT", "/F1 10 Tf", "14 TL", "50 792 Td"]
        for line in page_lines:
            content.append(f"({_pdf_escape(line)}) Tj")
            content.append("T*")
        content.append("ET")
        stream = "\n".join(content).encode("cp1252", errors="replace")
        content_id = add_object(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        page_id = add_object(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        page_ids.append(page_id)

    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)


def _pdf_escape(text: str) -> str:
    text = text.encode("cp1252", errors="replace").decode("cp1252")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _safe_stem(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")[:100]


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

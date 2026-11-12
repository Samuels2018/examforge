import re
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, defer

from app.models import Material, MaterialChunk
from app.models.enums import MaterialStatus

_FOCUS_STOPWORDS = {
    "para", "como", "sobre", "desde", "hasta", "entre", "cuando", "donde", "porque",
    "este", "esta", "estos", "estas", "tema", "temas", "ejercicio", "ejercicios",
}


@dataclass(frozen=True)
class MaterialWithCount:
    material: Material
    chunk_count: int


@dataclass(frozen=True)
class ContextRow:
    chunk_id: int
    content: str
    filename: str
    material_id: str


def get_material(session: Session, workspace_id: str, material_id: str) -> Material | None:
    return session.scalar(
        select(Material).where(
            Material.id == material_id,
            Material.workspace_id == workspace_id,
        )
    )


def list_materials_with_counts(
    session: Session, *, workspace_id: str, limit: int, offset: int
) -> tuple[list[MaterialWithCount], int]:
    total = (
        session.scalar(
            select(func.count(Material.id)).where(Material.workspace_id == workspace_id)
        )
        or 0
    )
    rows = session.execute(
        select(Material, func.count(MaterialChunk.id))
        .outerjoin(MaterialChunk, MaterialChunk.material_id == Material.id)
        .where(Material.workspace_id == workspace_id)
        .options(defer(Material.extracted_text))
        .group_by(Material.id)
        .order_by(Material.created_at.desc(), Material.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [MaterialWithCount(material=row[0], chunk_count=int(row[1])) for row in rows], total


def count_chunks_for_material(session: Session, material_id: str) -> int:
    return (
        session.scalar(
            select(func.count(MaterialChunk.id)).where(MaterialChunk.material_id == material_id)
        )
        or 0
    )


def ready_chunk_count(session: Session, workspace_id: str) -> int:
    return (
        session.scalar(
            select(func.count(MaterialChunk.id))
            .join(Material, MaterialChunk.material_id == Material.id)
            .where(
                MaterialChunk.workspace_id == workspace_id,
                Material.status == MaterialStatus.READY.value,
            )
        )
        or 0
    )


def get_context_rows(
    session: Session,
    *,
    workspace_id: str,
    focus: str | None,
    max_chunks: int = 120,
) -> list[ContextRow]:
    base = (
        select(
            MaterialChunk.id,
            MaterialChunk.content,
            Material.filename,
            Material.id,
        )
        .join(Material, MaterialChunk.material_id == Material.id)
        .where(
            MaterialChunk.workspace_id == workspace_id,
            Material.status == MaterialStatus.READY.value,
        )
    )

    keywords = _focus_keywords(focus)
    if keywords:
        clauses = [MaterialChunk.content.ilike(f"%{keyword}%") for keyword in keywords]
        rows = session.execute(
            base.where(or_(*clauses)).order_by(Material.id, MaterialChunk.idx).limit(max_chunks)
        ).all()
        if len(rows) >= 4:
            return [_to_context_row(row) for row in rows]

        general_rows = session.execute(
            base.order_by(Material.id, MaterialChunk.idx).limit(max_chunks)
        ).all()
        merged: dict[int, ContextRow] = {}
        for row in [*rows, *general_rows]:
            context_row = _to_context_row(row)
            merged.setdefault(context_row.chunk_id, context_row)
            if len(merged) >= max_chunks:
                break
        return list(merged.values())

    rows = session.execute(
        base.order_by(Material.id, MaterialChunk.idx).limit(max_chunks)
    ).all()
    return [_to_context_row(row) for row in rows]



def list_context_rows(
    session: Session,
    *,
    workspace_id: str,
    limit: int = 120,
) -> list[ContextRow]:
    """Candidatos sin filtro léxico; el reranking semántico decide el orden."""
    rows = session.execute(
        select(
            MaterialChunk.id,
            MaterialChunk.content,
            Material.filename,
            Material.id,
        )
        .join(Material, MaterialChunk.material_id == Material.id)
        .where(
            MaterialChunk.workspace_id == workspace_id,
            Material.status == MaterialStatus.READY.value,
        )
        .order_by(Material.id, MaterialChunk.idx)
        .limit(limit)
    ).all()
    return [_to_context_row(row) for row in rows]


def _to_context_row(row) -> ContextRow:
    return ContextRow(
        chunk_id=int(row[0]),
        content=row[1],
        filename=row[2],
        material_id=row[3],
    )


def _focus_keywords(focus: str | None) -> list[str]:
    if not focus:
        return []
    words = re.findall(r"[^\W\d_]{3,}", focus.casefold(), flags=re.UNICODE)
    return [word for word in dict.fromkeys(words) if word not in _FOCUS_STOPWORDS][:6]

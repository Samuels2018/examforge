from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChunkEmbedding


def embeddings_by_chunk(
    session: Session, *, chunk_ids: list[int], model: str
) -> dict[int, list[float]]:
    if not chunk_ids:
        return {}
    rows = session.execute(
        select(ChunkEmbedding.chunk_id, ChunkEmbedding.vector).where(
            ChunkEmbedding.chunk_id.in_(chunk_ids),
            ChunkEmbedding.model == model,
        )
    ).all()
    return {int(chunk_id): list(vector) for chunk_id, vector in rows}


def upsert_embeddings(
    session: Session,
    *,
    workspace_id: str,
    chunk_ids: list[int],
    vectors: list[list[float]],
    provider: str,
    model: str,
) -> None:
    if not chunk_ids:
        return
    existing = {
        row.chunk_id: row
        for row in session.scalars(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids))
        )
    }
    for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
        row = existing.get(chunk_id)
        if row is None:
            session.add(
                ChunkEmbedding(
                    chunk_id=chunk_id,
                    workspace_id=workspace_id,
                    provider=provider,
                    model=model,
                    dimensions=len(vector),
                    vector=vector,
                )
            )
        else:
            row.workspace_id = workspace_id
            row.provider = provider
            row.model = model
            row.dimensions = len(vector)
            row.vector = vector

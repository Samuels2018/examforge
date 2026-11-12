import logging
import math

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import EmbeddingUnavailableError
from app.repositories.embeddings import embeddings_by_chunk, upsert_embeddings
from app.repositories.materials import ContextRow, get_context_rows, list_context_rows
from app.services.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class ContextRetriever:
    """Recuperación híbrida: señales léxicas + embeddings, con reranking MMR."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        embedder: EmbeddingProvider,
    ) -> None:
        self.session = session
        self.settings = settings
        self.embedder = embedder

    def retrieve(self, *, workspace_id: str, focus: str | None) -> list[ContextRow]:
        if not self.settings.semantic_retrieval_enabled or not focus:
            return get_context_rows(
                self.session,
                workspace_id=workspace_id,
                focus=focus,
                max_chunks=self.settings.semantic_candidate_chunks,
            )

        rows = list_context_rows(
            self.session,
            workspace_id=workspace_id,
            limit=self.settings.semantic_candidate_chunks,
        )
        if len(rows) < 2:
            return rows

        try:
            query_batch = self.embedder.embed([focus])
            query_vector = query_batch.vectors[0]
            document_vectors = self._document_vectors(
                workspace_id,
                rows,
                cache_key=_batch_cache_key(query_batch),
                dimensions=len(query_vector),
            )
        except EmbeddingUnavailableError as exc:
            logger.warning("Embeddings no disponibles; se usa ranking léxico: %s", exc)
            return get_context_rows(
                self.session,
                workspace_id=workspace_id,
                focus=focus,
                max_chunks=self.settings.semantic_candidate_chunks,
            )

        focus_terms = _tokens(focus)
        relevance = [
            _hybrid_score(
                focus_terms=focus_terms,
                content=row.content,
                query_vector=query_vector,
                document_vector=document_vectors[row.chunk_id],
            )
            for row in rows
        ]
        selected = _mmr_select(
            rows=rows,
            relevance=relevance,
            vectors=document_vectors,
            limit=self.settings.semantic_context_chunks,
            mmr_lambda=self.settings.semantic_mmr_lambda,
        )
        return selected

    def _document_vectors(
        self,
        workspace_id: str,
        rows: list[ContextRow],
        *,
        cache_key: str,
        dimensions: int,
    ) -> dict[int, list[float]]:
        chunk_ids = [row.chunk_id for row in rows]
        cached = {
            chunk_id: vector
            for chunk_id, vector in embeddings_by_chunk(
                self.session, chunk_ids=chunk_ids, model=cache_key
            ).items()
            if len(vector) == dimensions
        }
        missing = [row for row in rows if row.chunk_id not in cached]
        if missing:
            batch = self.embedder.embed([row.content for row in missing])
            upsert_embeddings(
                self.session,
                workspace_id=workspace_id,
                chunk_ids=[row.chunk_id for row in missing],
                vectors=batch.vectors,
                provider=batch.provider,
                model=cache_key,
            )
            for row, vector in zip(missing, batch.vectors, strict=True):
                cached[row.chunk_id] = vector
        return {row.chunk_id: cached[row.chunk_id] for row in rows}


def _batch_cache_key(batch) -> str:
    if batch.provider == "offline":
        return batch.model
    return f"{batch.provider}:{batch.model}"


def _tokens(text: str) -> set[str]:
    from app.services.embeddings.offline import _terms

    return {term for term, weight in _terms(text) if weight >= 1.0}


def _hybrid_score(
    *,
    focus_terms: set[str],
    content: str,
    query_vector: list[float],
    document_vector: list[float],
) -> float:
    lexical = 0.0
    if focus_terms:
        content_terms = _tokens(content)
        lexical = len(focus_terms & content_terms) / len(focus_terms)
    semantic = max(0.0, _cosine(query_vector, document_vector))
    return 0.62 * semantic + 0.38 * lexical


def _mmr_select(
    *,
    rows: list[ContextRow],
    relevance: list[float],
    vectors: dict[int, list[float]],
    limit: int,
    mmr_lambda: float,
) -> list[ContextRow]:
    if len(rows) <= limit:
        return sorted(
            rows,
            key=lambda row: relevance[rows.index(row)],
            reverse=True,
        )

    remaining = list(range(len(rows)))
    selected: list[int] = []
    while remaining and len(selected) < limit:
        best_index = max(
            remaining,
            key=lambda index: _mmr_value(
                index=index,
                selected=selected,
                relevance=relevance,
                rows=rows,
                vectors=vectors,
                mmr_lambda=mmr_lambda,
            ),
        )
        selected.append(best_index)
        remaining.remove(best_index)
    return [rows[index] for index in selected]


def _mmr_value(
    *,
    index: int,
    selected: list[int],
    relevance: list[float],
    rows: list[ContextRow],
    vectors: dict[int, list[float]],
    mmr_lambda: float,
) -> float:
    if not selected:
        return relevance[index]
    max_similarity = max(
        _cosine(vectors[rows[index].chunk_id], vectors[rows[other].chunk_id])
        for other in selected
    )
    return mmr_lambda * relevance[index] - (1 - mmr_lambda) * max_similarity


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)

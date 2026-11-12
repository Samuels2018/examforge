import hashlib
import math
import re
import unicodedata

from app.services.embeddings.base import EmbeddingBatch, EmbeddingProvider

_WORD_RE = re.compile(r"[^\W\d_][\wáéíóúüñÁÉÍÓÚÜÑ-]*", re.UNICODE)
_STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "que", "en",
    "con", "por", "para", "del", "al", "se", "su", "sus", "es", "son", "como", "mas",
    "más", "pero", "sin", "sobre", "entre", "este", "esta", "estos", "estas", "ese",
    "esa", "esos", "esas", "lo", "le", "les", "me", "mi", "mis", "tu", "tus", "no",
    "sí", "si", "cuando", "donde", "porque", "también", "muy", "ya", "hay", "ser",
    "estar", "tiene", "tienen", "puede", "pueden", "desde", "hasta", "cada", "otro",
    "otra", "todo", "toda", "todos", "todas", "durante", "mediante", "según", "the",
    "and", "for", "with", "that", "this", "from", "are", "was", "were", "have", "has",
}


class OfflineEmbeddingProvider(EmbeddingProvider):
    """Embedding determinista por hashing de términos y trigramas.

    No requiere red ni modelos. No sustituye a un embedding neuronal, pero mejora
    mucho el ranking puramente léxico y permite funcionar offline de forma estable.
    """

    name = "offline"

    def __init__(self, *, dimensions: int = 384) -> None:
        self.dimensions = dimensions
        self.model = f"offline-hash-v1-{dimensions}"

    @property
    def cache_key(self) -> str:
        return self.model

    def available(self) -> bool:
        return True

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            vectors=[self._embed_one(text) for text in texts],
            provider=self.name,
            model=self.model,
        )

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for term, weight in _terms(text):
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 6) for value in vector]


def _terms(text: str) -> list[tuple[str, float]]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = [word for word in _WORD_RE.findall(normalized) if len(word) >= 2]
    terms: list[tuple[str, float]] = []
    for word in words:
        if word not in _STOPWORDS:
            terms.append((word, 1.0))
        if len(word) >= 5:
            padded = f"^{word}$"
            for index in range(len(padded) - 2):
                terms.append((padded[index : index + 3], 0.35))
    return terms

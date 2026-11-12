import httpx

from app.core.errors import EmbeddingUnavailableError
from app.services.embeddings.base import EmbeddingBatch, EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    name = "ollama"

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def cache_key(self) -> str:
        return f"ollama:{self.model}"

    def available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=1.5)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch([], self.name, self.model)
        try:
            response = httpx.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=self.timeout_seconds,
            )
            if response.status_code == 404:
                return self._embed_legacy(texts)
            response.raise_for_status()
            vectors = response.json().get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise ValueError("Ollama no devolvió un embedding por texto")
            return EmbeddingBatch(
                vectors=[_validate_vector(vector) for vector in vectors],
                provider=self.name,
                model=self.model,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise EmbeddingUnavailableError(
                f"No se pudieron calcular embeddings con Ollama ({self.model}).",
                details=str(exc),
            ) from exc

    def _embed_legacy(self, texts: list[str]) -> EmbeddingBatch:
        vectors: list[list[float]] = []
        for text in texts:
            response = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            vectors.append(_validate_vector(response.json().get("embedding")))
        return EmbeddingBatch(vectors=vectors, provider=self.name, model=self.model)


def _validate_vector(value: object) -> list[float]:
    if not isinstance(value, list) or not value:
        raise ValueError("Embedding vacío o inválido")
    return [float(item) for item in value]

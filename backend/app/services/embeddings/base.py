from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    provider: str
    model: str

    @property
    def dimensions(self) -> int:
        return len(self.vectors[0]) if self.vectors else 0


class EmbeddingProvider(ABC):
    name: str = "base"

    @property
    def cache_key(self) -> str:
        return self.name

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> EmbeddingBatch: ...

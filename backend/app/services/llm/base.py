from abc import ABC, abstractmethod

from app.models.enums import Difficulty
from app.schemas.llm import GenerationResult, GradeResult


class LLMProvider(ABC):
    """Contrato único para generar/corregir con cualquier motor."""

    name: str = "base"

    def available(self) -> bool:
        return True

    @abstractmethod
    def generate_exercises(
        self,
        *,
        context: str,
        count: int,
        difficulties: list[Difficulty],
        focus: str | None,
        language: str,
    ) -> GenerationResult: ...

    @abstractmethod
    def grade_short_answer(
        self,
        *,
        question: str,
        expected_answer: str,
        rubric: str | None,
        student_answer: str,
        language: str,
    ) -> GradeResult: ...

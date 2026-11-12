import logging

from app.core.errors import LLMUnavailableError
from app.models.enums import Difficulty
from app.schemas.llm import GenerationResult, GradeResult
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class AutoProvider(LLMProvider):
    """Intenta Ollama y, si no está disponible, usa el generador offline sin romper la UX."""

    name = "auto"

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def available(self) -> bool:
        return True

    def generate_exercises(
        self,
        *,
        context: str,
        count: int,
        difficulties: list[Difficulty],
        focus: str | None,
        language: str,
    ) -> GenerationResult:
        warning: str | None = None
        if self.primary.available():
            try:
                return self.primary.generate_exercises(
                    context=context,
                    count=count,
                    difficulties=difficulties,
                    focus=focus,
                    language=language,
                )
            except LLMUnavailableError as exc:
                logger.warning("Ollama falló; usando generador offline: %s", exc)
                warning = f"Ollama no respondió correctamente ({exc.message}). Se usó el generador offline."
        else:
            warning = (
                "Ollama no está disponible. Se usó el generador offline; "
                "levanta Ollama y descarga el modelo para ejercicios de mayor calidad."
            )

        result = self.fallback.generate_exercises(
            context=context,
            count=count,
            difficulties=difficulties,
            focus=focus,
            language=language,
        )
        result.warning = warning
        return result

    def grade_short_answer(
        self,
        *,
        question: str,
        expected_answer: str,
        rubric: str | None,
        student_answer: str,
        language: str,
    ) -> GradeResult:
        if self.primary.available():
            try:
                return self.primary.grade_short_answer(
                    question=question,
                    expected_answer=expected_answer,
                    rubric=rubric,
                    student_answer=student_answer,
                    language=language,
                )
            except LLMUnavailableError as exc:
                logger.warning("Ollama falló corrigiendo; usando corrección offline: %s", exc)
                result = self._fallback_grade(
                    question, expected_answer, rubric, student_answer, language
                )
                result.warning = f"Corrección heurística: Ollama no respondió ({exc.message})."
                return result

        result = self._fallback_grade(question, expected_answer, rubric, student_answer, language)
        result.warning = "Corrección heurística: Ollama no está disponible."
        return result

    def _fallback_grade(
        self,
        question: str,
        expected_answer: str,
        rubric: str | None,
        student_answer: str,
        language: str,
    ) -> GradeResult:
        return self.fallback.grade_short_answer(
            question=question,
            expected_answer=expected_answer,
            rubric=rubric,
            student_answer=student_answer,
            language=language,
        )

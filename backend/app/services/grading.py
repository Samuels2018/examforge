from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Attempt, Exercise, new_id
from app.models.enums import ExerciseKind
from app.repositories.exercises import get_exercise
from app.schemas.exercise import AttemptCreate, AttemptResult
from app.services.diagnostics import DiagnosticService
from app.services.llm.base import LLMProvider
from app.services.mastery import MasteryService

_TRUE_VALUES = {"true", "verdadero", "verdadera", "v", "si", "sí"}
_FALSE_VALUES = {"false", "falso", "falsa", "f", "no"}


class AttemptService:
    def __init__(self, session: Session, provider: LLMProvider) -> None:
        self.session = session
        self.provider = provider

    def submit(
        self,
        *,
        workspace_id: str,
        exercise_id: str,
        payload: AttemptCreate,
    ) -> AttemptResult:
        exercise = get_exercise(self.session, workspace_id, exercise_id)
        if exercise is None:
            raise NotFoundError("Ejercicio no encontrado")

        result = self.grade(exercise, payload.answer)

        attempt = Attempt(
            id=new_id(),
            exercise_id=exercise.id,
            workspace_id=workspace_id,
            answer=payload.answer.strip(),
            is_correct=result["is_correct"],
            score=result["score"],
            feedback=result["feedback"],
            explanation=result["explanation"],
            duration_seconds=payload.duration_seconds,
        )
        self.session.add(attempt)
        self.session.flush()
        MasteryService(self.session).record_attempt(
            workspace_id=workspace_id,
            exercise=exercise,
            score=result["score"],
            is_correct=result["is_correct"],
        )
        DiagnosticService(self.session).record(
            workspace_id=workspace_id,
            attempt=attempt,
            exercise=exercise,
            score=result["score"],
            is_correct=result["is_correct"],
        )
        self.session.commit()

        return AttemptResult(
            attempt_id=attempt.id,
            exercise_id=exercise.id,
            is_correct=result["is_correct"],
            score=result["score"],
            correct_answer=_display_correct_answer(exercise),
            feedback=result["feedback"],
            explanation=result["explanation"],
            provider=result["provider"],
            warning=result.get("warning"),
        )

    def grade(self, exercise: Exercise, answer: str) -> dict:
        if exercise.kind == ExerciseKind.MULTIPLE_CHOICE.value:
            return self._grade_multiple_choice(exercise, answer)
        if exercise.kind == ExerciseKind.TRUE_FALSE.value:
            return self._grade_true_false(exercise, answer)
        return self._grade_short_answer(exercise, answer)

    def _grade_multiple_choice(self, exercise: Exercise, answer: str) -> dict:
        options = exercise.options or []
        normalized = answer.strip().casefold()
        chosen_id = None
        for option in options:
            if normalized in {str(option.get("id", "")).casefold(), str(option.get("text", "")).casefold()}:
                chosen_id = str(option.get("id"))
                break

        is_correct = chosen_id == exercise.correct_answer
        correct_text = _option_text(options, exercise.correct_answer)
        if is_correct:
            feedback = "¡Correcto! Has identificado la opción adecuada."
        else:
            feedback = (
                f"No es correcto. La respuesta correcta es la opción {exercise.correct_answer}"
                f": «{correct_text}»." if correct_text else "No es correcto."
            )
        return {
            "is_correct": is_correct,
            "score": 1.0 if is_correct else 0.0,
            "feedback": feedback,
            "explanation": exercise.explanation,
            "provider": "deterministic",
        }

    def _grade_true_false(self, exercise: Exercise, answer: str) -> dict:
        normalized = answer.strip().casefold()
        if normalized in _TRUE_VALUES:
            chosen = "true"
        elif normalized in _FALSE_VALUES:
            chosen = "false"
        else:
            return {
                "is_correct": False,
                "score": 0.0,
                "feedback": "Respuesta no válida: elige «Verdadero» o «Falso».",
                "explanation": exercise.explanation,
                "provider": "deterministic",
            }

        is_correct = chosen == exercise.correct_answer
        correct_label = "Verdadero" if exercise.correct_answer == "true" else "Falso"
        feedback = (
            "¡Correcto!"
            if is_correct
            else f"No es correcto. La afirmación es {correct_label}."
        )
        return {
            "is_correct": is_correct,
            "score": 1.0 if is_correct else 0.0,
            "feedback": feedback,
            "explanation": exercise.explanation,
            "provider": "deterministic",
        }

    def _grade_short_answer(self, exercise: Exercise, answer: str) -> dict:
        result = self.provider.grade_short_answer(
            question=exercise.question,
            expected_answer=exercise.correct_answer,
            rubric=exercise.rubric,
            student_answer=answer,
            language="es",
        )
        explanation = result.explanation.strip()
        if exercise.explanation and exercise.explanation.strip() not in explanation:
            explanation = f"{explanation}\n\n{exercise.explanation.strip()}".strip()
        return {
            "is_correct": result.is_correct,
            "score": max(0.0, min(1.0, result.score)),
            "feedback": result.feedback,
            "explanation": explanation,
            "provider": result.provider,
            "warning": result.warning,
        }


def _option_text(options: list[dict], option_id: str) -> str:
    for option in options:
        if str(option.get("id")) == option_id:
            return str(option.get("text", ""))
    return ""


def _display_correct_answer(exercise: Exercise) -> str:
    if exercise.kind == ExerciseKind.MULTIPLE_CHOICE.value:
        text = _option_text(exercise.options or [], exercise.correct_answer)
        return f"{exercise.correct_answer}: {text}" if text else exercise.correct_answer
    if exercise.kind == ExerciseKind.TRUE_FALSE.value:
        return "Verdadero" if exercise.correct_answer == "true" else "Falso"
    return exercise.correct_answer

import re
import unicodedata

from sqlalchemy.orm import Session

from app.models import Attempt, AttemptDiagnostic, Exercise, new_id
from app.models.enums import ExerciseKind
from app.repositories.mastery import list_error_patterns
from app.schemas.mastery import ErrorPattern

_STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "que", "en",
    "con", "por", "para", "del", "al", "se", "su", "sus", "es", "son", "como", "mas",
    "más", "pero", "sin", "sobre", "entre", "este", "esta", "estos", "estas", "ese",
    "esa", "esos", "esas", "lo", "le", "les", "me", "mi", "mis", "tu", "tus", "no",
    "sí", "si", "cuando", "donde", "porque", "también", "muy", "ya", "hay", "ser",
    "estar", "tiene", "tienen", "puede", "pueden", "desde", "hasta", "cada", "otro",
    "otra", "todo", "toda", "todos", "todas", "durante", "mediante", "según",
}


class DiagnosticService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        workspace_id: str,
        attempt: Attempt,
        exercise: Exercise,
        score: float,
        is_correct: bool,
    ) -> AttemptDiagnostic | None:
        classified = classify_error(
            exercise=exercise,
            answer=attempt.answer,
            score=score,
            is_correct=is_correct,
        )
        if classified is None:
            return None
        error_type, detail = classified
        diagnostic = AttemptDiagnostic(
            id=new_id(),
            attempt_id=attempt.id,
            workspace_id=workspace_id,
            topic=exercise.topic[:200],
            error_type=error_type,
            detail=detail,
        )
        self.session.add(diagnostic)
        return diagnostic

    def patterns(self, workspace_id: str, *, min_count: int = 1) -> list[ErrorPattern]:
        return [
            ErrorPattern(
                topic=row.topic,
                error_type=row.error_type,
                count=row.count,
                detail=row.detail,
                last_seen_at=row.last_seen_at,
            )
            for row in list_error_patterns(
                self.session, workspace_id=workspace_id, min_count=min_count
            )
        ]


def classify_error(
    *,
    exercise: Exercise,
    answer: str,
    score: float,
    is_correct: bool,
) -> tuple[str, str] | None:
    if is_correct:
        return None
    answer = answer.strip()
    if not answer:
        return "sin_respuesta", "Entregó la pregunta sin responder."

    if exercise.kind == ExerciseKind.MULTIPLE_CHOICE.value:
        chosen = _option_text(exercise.options or [], answer)
        correct = _option_text(exercise.options or [], exercise.correct_answer)
        detail = f"Eligió «{chosen or answer}»"
        if correct:
            detail += f" en lugar de «{correct}»."
        return "seleccion_incorrecta", detail

    if exercise.kind == ExerciseKind.TRUE_FALSE.value:
        correct_label = "Verdadero" if exercise.correct_answer == "true" else "Falso"
        return "confusion_verdadero_falso", f"Respondió «{answer}»; la afirmación es {correct_label}."

    missing = _missing_concepts(exercise.correct_answer, answer)
    if score <= 0:
        detail = "No aparece la idea central."
        if missing:
            detail += f" Faltó: {', '.join(missing[:4])}."
        return "concepto_ausente", detail
    detail = "La idea principal aparece, pero falta precisión."
    if missing:
        detail += f" Faltó: {', '.join(missing[:4])}."
    return "respuesta_incompleta", detail


def _missing_concepts(expected: str, answer: str) -> list[str]:
    expected_terms = _terms(expected)
    answer_terms = _terms(answer)
    return [term for term in expected_terms if term not in answer_terms][:6]


def _terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-z0-9]{3,}", normalized.casefold())
    return list(dict.fromkeys(word for word in words if word not in _STOPWORDS))


def _option_text(options: list[dict], value: str) -> str:
    normalized = value.casefold()
    for option in options:
        if str(option.get("id", "")).casefold() == normalized:
            return str(option.get("text", ""))
        if str(option.get("text", "")).casefold() == normalized:
            return str(option.get("text", ""))
    return ""

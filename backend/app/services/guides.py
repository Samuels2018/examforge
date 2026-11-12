import re
from datetime import UTC

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Exercise, ExerciseGuide, new_id
from app.repositories.exercises import get_exercise
from app.repositories.guides import get_guide
from app.repositories.mastery import list_error_patterns
from app.repositories.materials import get_context_rows
from app.schemas.guide import GuideRead, GuideStep
from app.services.mastery import topic_key

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")


class GuideService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(self, workspace_id: str, exercise_id: str) -> GuideRead:
        exercise = get_exercise(self.session, workspace_id, exercise_id)
        if exercise is None:
            raise NotFoundError("Ejercicio no encontrado")

        existing = get_guide(self.session, exercise.id)
        if existing is not None:
            return _to_read(existing)

        rows = get_context_rows(
            self.session,
            workspace_id=workspace_id,
            focus=exercise.topic,
            max_chunks=12,
        )
        concept = exercise.explanation.strip() or _first_sentence(rows, exercise.topic)
        example = _example(rows, exercise.topic, fallback=concept)
        steps = self._build_steps(workspace_id, exercise, example)

        guide = ExerciseGuide(
            id=new_id(),
            exercise_id=exercise.id,
            workspace_id=workspace_id,
            concept=concept,
            example=example,
            steps=[step.model_dump() for step in steps],
            provider="deterministic",
        )
        self.session.add(guide)
        self.session.commit()
        return _to_read(guide)

    def _build_steps(
        self, workspace_id: str, exercise: Exercise, example: str
    ) -> list[GuideStep]:
        steps = [
            GuideStep(
                title="1. Reconoce el concepto",
                detail=exercise.explanation.strip() or example,
            ),
            GuideStep(
                title="2. Aplica el procedimiento",
                detail=(
                    exercise.hint.strip()
                    if exercise.hint
                    else "Identifica qué te piden, qué datos tienes y qué regla conecta ambos."
                ),
            ),
            GuideStep(
                title="3. Comprueba tu razonamiento",
                detail=(
                    f"La respuesta correcta es «{_display_answer(exercise)}». "
                    "Explica en voz alta por qué las demás opciones no encajan."
                ),
            ),
        ]
        pattern = next(
            (
                item
                for item in list_error_patterns(
                    self.session, workspace_id=workspace_id, min_count=1
                )
                if topic_key(item.topic) == topic_key(exercise.topic)
            ),
            None,
        )
        if pattern is not None:
            steps.append(
                GuideStep(
                    title="4. Evita repetir el error",
                    detail=f"Patrón detectado en este tema: {pattern.detail}",
                )
            )
        else:
            steps.append(
                GuideStep(
                    title="4. Fija el aprendizaje",
                    detail=(
                        "Cierra la guía y vuelve a responder una variación sin mirar. "
                        "Si vuelves a fallar, revisa el paso 1 antes de intentarlo otra vez."
                    ),
                )
            )
        return steps


def _example(rows, topic: str, *, fallback: str) -> str:
    normalized_topic = topic.casefold()
    for row in rows:
        for sentence in _SENTENCE_SPLIT.split(row.content):
            cleaned = " ".join(sentence.split()).strip()
            if 40 <= len(cleaned) <= 420 and (
                normalized_topic in cleaned.casefold()
                or any(term in cleaned.casefold() for term in normalized_topic.split() if len(term) > 3)
            ):
                return cleaned
    return _first_sentence(rows, topic) or fallback


def _first_sentence(rows, topic: str) -> str:
    for row in rows:
        for sentence in _SENTENCE_SPLIT.split(row.content):
            cleaned = " ".join(sentence.split()).strip()
            if len(cleaned) >= 40:
                return cleaned[:420]
    return f"Repasa el material relacionado con «{topic}» antes de volver a intentarlo."


def _display_answer(exercise: Exercise) -> str:
    if exercise.kind == "multiple_choice":
        for option in exercise.options or []:
            if str(option.get("id")) == exercise.correct_answer:
                return str(option.get("text", exercise.correct_answer))
        return exercise.correct_answer
    if exercise.kind == "true_false":
        return "Verdadero" if exercise.correct_answer == "true" else "Falso"
    return exercise.correct_answer


def _to_read(guide: ExerciseGuide) -> GuideRead:
    return GuideRead(
        exercise_id=guide.exercise_id,
        concept=guide.concept,
        example=guide.example,
        steps=[GuideStep.model_validate(step) for step in guide.steps],
        provider=guide.provider,
        created_at=(
            guide.created_at
            if guide.created_at.tzinfo is not None
            else guide.created_at.replace(tzinfo=UTC)
        ),
    )

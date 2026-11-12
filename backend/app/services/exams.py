from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import InvalidMaterialError, NotFoundError
from app.models import (
    Attempt,
    ExamSession,
    ExamSessionItem,
    Exercise,
    new_id,
    utcnow,
)
from app.models.enums import Difficulty, ExerciseKind
from app.repositories.exercises import list_exercises
from app.repositories.workspaces import get_workspace
from app.schemas.exam import (
    ExamQuestionRead,
    ExamRead,
    ExamResult,
    ExamResultItem,
    ExamStartRequest,
    ExamSubmitRequest,
)
from app.schemas.exercise import ExerciseOption
from app.services.diagnostics import DiagnosticService
from app.services.grading import AttemptService
from app.services.llm.base import LLMProvider
from app.services.mastery import MasteryService, MasteryUpdate

ExamStatus = Literal["active", "submitted", "expired"]


class ExamService:
    def __init__(self, session: Session, settings: Settings, provider: LLMProvider) -> None:
        self.session = session
        self.settings = settings
        self.provider = provider

    def create(self, workspace_id: str, payload: ExamStartRequest) -> ExamRead:
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")
        count = min(payload.count, self.settings.exam_max_questions)
        exercises, _total = list_exercises(
            self.session,
            workspace_id=workspace_id,
            difficulty=None,
            kind=None,
            limit=200,
            offset=0,
        )
        allowed = {difficulty.value for difficulty in payload.difficulties}
        selected = [exercise for exercise in exercises if exercise.difficulty in allowed][:count]
        if len(selected) < count:
            raise InvalidMaterialError(
                f"Necesitas al menos {count} ejercicios de las dificultades elegidas. "
                f"Solo hay {len(selected)}. Genera más ejercicios antes de empezar el examen."
            )

        minutes = payload.time_limit_minutes or self.settings.exam_default_minutes
        now = utcnow()
        exam = ExamSession(
            id=new_id(),
            workspace_id=workspace_id,
            status="active",
            difficulties=[difficulty.value for difficulty in payload.difficulties],
            time_limit_seconds=minutes * 60,
            total_questions=len(selected),
            started_at=now,
            expires_at=now + timedelta(minutes=minutes),
        )
        self.session.add(exam)
        for position, exercise in enumerate(selected, start=1):
            self.session.add(
                ExamSessionItem(
                    id=new_id(),
                    session_id=exam.id,
                    exercise_id=exercise.id,
                    position=position,
                    kind=exercise.kind,
                    difficulty=exercise.difficulty,
                    topic=exercise.topic,
                    question=exercise.question,
                    options=[dict(option) for option in (exercise.options or [])],
                    correct_answer=exercise.correct_answer,
                    explanation=exercise.explanation,
                    rubric=exercise.rubric,
                )
            )
        self.session.commit()
        return self._read(exam, self._items(exam.id))

    def get(self, workspace_id: str, exam_id: str) -> ExamRead:
        exam = self._get_session(workspace_id, exam_id)
        return self._read(exam, self._items(exam.id))

    def submit(
        self, workspace_id: str, exam_id: str, payload: ExamSubmitRequest
    ) -> ExamResult:
        exam = self._get_session(workspace_id, exam_id)
        items = self._items(exam.id)
        if exam.status in {"submitted", "expired"}:
            return self._result(exam, items)

        answers = {answer.item_id: answer.answer for answer in payload.answers}
        unknown = set(answers) - {item.id for item in items}
        if unknown:
            raise InvalidMaterialError("El examen contiene respuestas para preguntas desconocidas.")

        grader = AttemptService(self.session, self.provider)
        now = utcnow()
        attempts: list[Attempt] = []
        diagnostics = DiagnosticService(self.session)
        mastery_updates: list[MasteryUpdate] = []

        for item in items:
            answer = answers.get(item.id, "")
            exercise = _snapshot_exercise(item, workspace_id)
            result = grader.grade(exercise, answer)
            item.answer = answer.strip()
            item.is_correct = result["is_correct"]
            item.score = result["score"]
            item.feedback = result["feedback"]
            attempt = Attempt(
                id=new_id(),
                exercise_id=item.exercise_id,
                workspace_id=workspace_id,
                answer=answer.strip(),
                is_correct=result["is_correct"],
                score=result["score"],
                feedback=result["feedback"],
                explanation=result["explanation"],
                duration_seconds=None,
            )
            attempts.append(attempt)
            mastery_updates.append(
                MasteryUpdate(
                    topic=item.topic,
                    score=result["score"],
                    is_correct=result["is_correct"],
                )
            )

        self.session.add_all(attempts)
        self.session.flush()
        for attempt, item in zip(attempts, items, strict=True):
            diagnostics.record(
                workspace_id=workspace_id,
                attempt=attempt,
                exercise=_snapshot_exercise(item, workspace_id),
                score=item.score or 0.0,
                is_correct=bool(item.is_correct),
            )
        MasteryService(self.session).record_many(
            workspace_id=workspace_id, updates=mastery_updates
        )

        exam.correct_count = sum(1 for item in items if item.is_correct)
        exam.score = round(
            sum(item.score or 0.0 for item in items) / len(items), 3
        ) if items else 0.0
        exam.duration_seconds = (
            payload.duration_seconds
            if payload.duration_seconds is not None
            else max(0, int((now - _aware(exam.started_at)).total_seconds()))
        )
        late = now > _aware(exam.expires_at)
        exam.status = "expired" if late else "submitted"
        exam.submitted_at = now
        self.session.commit()
        return self._result(exam, items)

    def _get_session(self, workspace_id: str, exam_id: str) -> ExamSession:
        exam = self.session.scalar(
            select(ExamSession).where(
                ExamSession.id == exam_id,
                ExamSession.workspace_id == workspace_id,
            )
        )
        if exam is None:
            raise NotFoundError("Examen no encontrado")
        return exam

    def _items(self, exam_id: str) -> list[ExamSessionItem]:
        return list(
            self.session.scalars(
                select(ExamSessionItem)
                .where(ExamSessionItem.session_id == exam_id)
                .order_by(ExamSessionItem.position)
            )
        )

    def _read(self, exam: ExamSession, items: list[ExamSessionItem]) -> ExamRead:
        now = utcnow()
        expires = _aware(exam.expires_at)
        status = exam.status
        if status == "active" and now >= expires:
            status = "expired"
        return ExamRead(
            id=exam.id,
            workspace_id=exam.workspace_id,
            status=cast(ExamStatus, status),
            time_limit_seconds=exam.time_limit_seconds,
            total_questions=exam.total_questions,
            correct_count=exam.correct_count,
            score=exam.score,
            duration_seconds=exam.duration_seconds,
            started_at=_aware(exam.started_at),
            expires_at=expires,
            submitted_at=_aware(exam.submitted_at) if exam.submitted_at else None,
            seconds_remaining=max(0, int((expires - now).total_seconds())),
            questions=[
                ExamQuestionRead(
                    id=item.id,
                    position=item.position,
                    kind=ExerciseKind(item.kind),
                    difficulty=Difficulty(item.difficulty),
                    topic=item.topic,
                    question=item.question,
                    options=cast(list[ExerciseOption], item.options or []),
                    answer=item.answer,
                )
                for item in items
            ],
        )

    def _result(self, exam: ExamSession, items: list[ExamSessionItem]) -> ExamResult:
        return ExamResult(
            id=exam.id,
            workspace_id=exam.workspace_id,
            status=cast(ExamStatus, exam.status),
            total_questions=exam.total_questions,
            correct_count=exam.correct_count,
            score=exam.score,
            duration_seconds=exam.duration_seconds,
            time_limit_seconds=exam.time_limit_seconds,
            started_at=_aware(exam.started_at),
            submitted_at=_aware(exam.submitted_at) if exam.submitted_at else None,
            items=[
                ExamResultItem(
                    id=item.id,
                    position=item.position,
                    kind=ExerciseKind(item.kind),
                    difficulty=Difficulty(item.difficulty),
                    topic=item.topic,
                    question=item.question,
                    options=cast(list[ExerciseOption], item.options or []),
                    answer=item.answer,
                    is_correct=bool(item.is_correct),
                    score=item.score or 0.0,
                    feedback=item.feedback or "",
                    correct_answer=_display_answer(item),
                    explanation=item.explanation,
                )
                for item in items
            ],
        )


def _snapshot_exercise(item: ExamSessionItem, workspace_id: str) -> Exercise:
    return Exercise(
        id=item.exercise_id,
        workspace_id=workspace_id,
        topic=item.topic,
        difficulty=item.difficulty,
        kind=item.kind,
        question=item.question,
        options=item.options or [],
        correct_answer=item.correct_answer,
        explanation=item.explanation,
        hint=None,
        rubric=item.rubric,
        source_material_ids=[],
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _display_answer(item: ExamSessionItem) -> str:
    if item.kind == "multiple_choice":
        for option in item.options or []:
            if str(option.get("id")) == item.correct_answer:
                text = str(option.get("text", ""))
                return f"{item.correct_answer}: {text}" if text else item.correct_answer
        return item.correct_answer
    if item.kind == "true_false":
        return "Verdadero" if item.correct_answer == "true" else "Falso"
    return item.correct_answer

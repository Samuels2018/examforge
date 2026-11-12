from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Attempt, Exercise
from app.models.enums import Difficulty, ExerciseKind
from app.schemas.exercise import AttemptHistoryItem
from app.services.pagination import decode_cursor, encode_cursor


def get_exercise(session: Session, workspace_id: str, exercise_id: str) -> Exercise | None:
    return session.scalar(
        select(Exercise).where(
            Exercise.id == exercise_id,
            Exercise.workspace_id == workspace_id,
        )
    )


def list_exercises(
    session: Session,
    *,
    workspace_id: str,
    difficulty: Difficulty | None,
    kind: ExerciseKind | None,
    limit: int,
    offset: int,
) -> tuple[list[Exercise], int]:
    filters = [Exercise.workspace_id == workspace_id]
    if difficulty is not None:
        filters.append(Exercise.difficulty == difficulty.value)
    if kind is not None:
        filters.append(Exercise.kind == kind.value)

    total = session.scalar(select(func.count(Exercise.id)).where(*filters)) or 0
    items = session.scalars(
        select(Exercise)
        .where(*filters)
        .order_by(Exercise.created_at.desc(), Exercise.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def existing_exercise_signatures(session: Session, workspace_id: str) -> list[str]:
    return list(
        session.scalars(
            select(Exercise.signature).where(
                Exercise.workspace_id == workspace_id,
                Exercise.signature.is_not(None),
            )
        )
    )


def list_attempt_history(
    session: Session,
    *,
    workspace_id: str,
    limit: int,
    offset: int = 0,
    cursor: str | None = None,
) -> tuple[list[AttemptHistoryItem], int, str | None]:
    total = (
        session.scalar(
            select(func.count(Attempt.id)).where(Attempt.workspace_id == workspace_id)
        )
        or 0
    )
    filters = [Attempt.workspace_id == workspace_id]
    if cursor:
        created_at, item_id = decode_cursor(cursor)
        filters.append(
            or_(
                Attempt.created_at < created_at,
                and_(Attempt.created_at == created_at, Attempt.id < item_id),
            )
        )

    query = (
        select(
            Attempt.id,
            Attempt.exercise_id,
            Exercise.question,
            Exercise.topic,
            Exercise.difficulty,
            Exercise.kind,
            Attempt.answer,
            Attempt.is_correct,
            Attempt.score,
            Attempt.created_at,
        )
        .join(Exercise, Attempt.exercise_id == Exercise.id)
        .where(*filters)
        .order_by(Attempt.created_at.desc(), Attempt.id)
        .limit(limit + 1)
    )
    if not cursor:
        query = query.offset(offset)
    rows = session.execute(query).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        AttemptHistoryItem(
            id=row[0],
            exercise_id=row[1],
            question=row[2],
            topic=row[3],
            difficulty=Difficulty(row[4]),
            kind=ExerciseKind(row[5]),
            answer=row[6],
            is_correct=row[7],
            score=row[8],
            created_at=row[9],
        )
        for row in rows
    ]
    next_cursor = None
    if has_more and rows:
        next_cursor = encode_cursor(rows[-1][9], rows[-1][0])
    return items, total, next_cursor


def recent_attempts(
    session: Session, *, workspace_id: str, limit: int = 8
) -> list[AttemptHistoryItem]:
    items, _, _ = list_attempt_history(
        session, workspace_id=workspace_id, limit=limit, offset=0
    )
    return items

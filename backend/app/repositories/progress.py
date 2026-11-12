from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Attempt, Exercise


@dataclass(frozen=True)
class GroupStats:
    key: str
    attempts: int
    correct: int


@dataclass(frozen=True)
class OverallStats:
    total_exercises: int
    attempted_exercises: int
    attempts: int
    correct: int


def overall_stats(session: Session, workspace_id: str) -> OverallStats:
    total_exercises = (
        session.scalar(
            select(func.count(Exercise.id)).where(Exercise.workspace_id == workspace_id)
        )
        or 0
    )
    attempted_exercises = (
        session.scalar(
            select(func.count(func.distinct(Attempt.exercise_id))).where(
                Attempt.workspace_id == workspace_id
            )
        )
        or 0
    )
    attempts, correct = session.execute(
        select(
            func.count(Attempt.id),
            func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)),
        ).where(Attempt.workspace_id == workspace_id)
    ).one()
    return OverallStats(
        total_exercises=int(total_exercises),
        attempted_exercises=int(attempted_exercises),
        attempts=int(attempts or 0),
        correct=int(correct or 0),
    )


def stats_by_difficulty(session: Session, workspace_id: str) -> list[GroupStats]:
    rows = session.execute(
        select(
            Exercise.difficulty,
            func.count(Attempt.id),
            func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)),
        )
        .join(Exercise, Attempt.exercise_id == Exercise.id)
        .where(Attempt.workspace_id == workspace_id)
        .group_by(Exercise.difficulty)
    ).all()
    return [GroupStats(key=row[0], attempts=int(row[1] or 0), correct=int(row[2] or 0)) for row in rows]


def stats_by_topic(session: Session, workspace_id: str) -> list[GroupStats]:
    rows = session.execute(
        select(
            Exercise.topic,
            func.count(Attempt.id),
            func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)),
        )
        .join(Exercise, Attempt.exercise_id == Exercise.id)
        .where(Attempt.workspace_id == workspace_id)
        .group_by(Exercise.topic)
    ).all()
    return [GroupStats(key=row[0], attempts=int(row[1] or 0), correct=int(row[2] or 0)) for row in rows]

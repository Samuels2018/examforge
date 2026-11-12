from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExerciseGuide


def get_guide(session: Session, exercise_id: str) -> ExerciseGuide | None:
    return session.scalar(select(ExerciseGuide).where(ExerciseGuide.exercise_id == exercise_id))

from pydantic import BaseModel

from app.schemas.exercise import GeneratedExercise
from app.schemas.usage import TokenUsage


class GenerationResult(BaseModel):
    exercises: list[GeneratedExercise]
    provider: str
    warning: str | None = None
    usage: TokenUsage | None = None


class GradeResult(BaseModel):
    score: float
    is_correct: bool
    feedback: str
    explanation: str
    provider: str
    warning: str | None = None

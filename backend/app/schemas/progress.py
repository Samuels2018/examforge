from datetime import datetime

from pydantic import BaseModel

from app.models.enums import Difficulty
from app.schemas.mastery import ErrorPattern, TopicMasteryRead

# Nota: los intentos se calculan por tema/dificultad con agregaciones SQL,
# no cargando relaciones (evita N+1).


class TopicStat(BaseModel):
    topic: str
    attempts: int
    correct: int
    accuracy: float


class DifficultyStat(BaseModel):
    difficulty: Difficulty
    attempts: int
    correct: int
    accuracy: float


class RecentAttempt(BaseModel):
    id: str
    exercise_id: str
    question: str
    topic: str
    difficulty: Difficulty
    answer: str
    is_correct: bool
    score: float
    created_at: datetime


class ProgressRead(BaseModel):
    workspace_id: str
    total_exercises: int
    attempted_exercises: int
    total_attempts: int
    correct_attempts: int
    accuracy: float
    by_difficulty: list[DifficultyStat]
    by_topic: list[TopicStat]
    weak_topics: list[TopicStat]
    recent_attempts: list[RecentAttempt]
    mastery: list[TopicMasteryRead] = []
    due_topics: list[TopicMasteryRead] = []
    error_patterns: list[ErrorPattern] = []
    average_mastery: float = 0.0


class PlanStep(BaseModel):
    title: str
    reason: str
    action: str
    focus_topic: str | None = None
    suggested_difficulty: Difficulty = Difficulty.BASIC
    suggested_count: int = 3


class StudyPlan(BaseModel):
    workspace_id: str
    summary: str
    steps: list[PlanStep]
    weak_topics: list[TopicStat]
    due_topics: list[TopicMasteryRead] = []
    error_patterns: list[ErrorPattern] = []
    generated_at: datetime

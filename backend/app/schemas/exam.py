from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import Difficulty, ExerciseKind
from app.schemas.exercise import ExerciseOption

ExamStatus = Literal["active", "submitted", "expired"]


class ExamStartRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)
    difficulties: list[Difficulty] = Field(
        default_factory=lambda: [Difficulty.BASIC, Difficulty.INTERMEDIATE, Difficulty.ADVANCED],
        min_length=1,
        max_length=3,
    )
    time_limit_minutes: int | None = Field(default=None, ge=5, le=240)

    @field_validator("difficulties")
    @classmethod
    def unique_difficulties(cls, value: list[Difficulty]) -> list[Difficulty]:
        return list(dict.fromkeys(value))


class ExamQuestionRead(BaseModel):
    id: str
    position: int
    kind: ExerciseKind
    difficulty: Difficulty
    topic: str
    question: str
    options: list[ExerciseOption]
    answer: str = ""


class ExamRead(BaseModel):
    id: str
    workspace_id: str
    status: ExamStatus
    time_limit_seconds: int
    total_questions: int
    correct_count: int
    score: float
    duration_seconds: int | None
    started_at: datetime
    expires_at: datetime
    submitted_at: datetime | None
    seconds_remaining: int
    questions: list[ExamQuestionRead]


class ExamAnswer(BaseModel):
    item_id: str = Field(min_length=1, max_length=32)
    answer: str = Field(default="", max_length=8_000)


class ExamSubmitRequest(BaseModel):
    answers: list[ExamAnswer] = Field(default_factory=list, max_length=100)
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)


class ExamResultItem(BaseModel):
    id: str
    position: int
    kind: ExerciseKind
    difficulty: Difficulty
    topic: str
    question: str
    options: list[ExerciseOption]
    answer: str
    is_correct: bool
    score: float
    feedback: str
    correct_answer: str
    explanation: str


class ExamResult(BaseModel):
    id: str
    workspace_id: str
    status: ExamStatus
    total_questions: int
    correct_count: int
    score: float
    duration_seconds: int | None
    time_limit_seconds: int
    started_at: datetime
    submitted_at: datetime | None
    items: list[ExamResultItem]

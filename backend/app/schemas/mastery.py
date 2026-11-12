from datetime import datetime

from pydantic import BaseModel, Field


class TopicMasteryRead(BaseModel):
    topic: str
    topic_key: str
    attempts: int
    correct: int
    accuracy: float = Field(ge=0.0, le=1.0)
    mastery: float = Field(ge=0.0, le=1.0)
    streak: int
    interval_days: int
    due_at: datetime
    last_attempt_at: datetime | None
    is_due: bool


class MasteryOverview(BaseModel):
    workspace_id: str
    topics: list[TopicMasteryRead]
    due_topics: list[TopicMasteryRead]
    average_mastery: float = Field(ge=0.0, le=1.0)


class ErrorPattern(BaseModel):
    topic: str
    error_type: str
    count: int
    detail: str
    last_seen_at: datetime

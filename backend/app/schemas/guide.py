from datetime import datetime

from pydantic import BaseModel, Field


class GuideStep(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=4_000)


class GuideRead(BaseModel):
    exercise_id: str
    concept: str
    example: str
    steps: list[GuideStep]
    provider: str
    created_at: datetime

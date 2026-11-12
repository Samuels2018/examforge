from datetime import datetime

from pydantic import BaseModel, Field


class BackupRead(BaseModel):
    filename: str
    size_bytes: int
    created_at: datetime


class RestoreRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)

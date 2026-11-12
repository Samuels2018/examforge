from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MaterialStatus


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: MaterialStatus
    char_count: int
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime


class MaterialDetail(MaterialRead):
    preview: str = ""


class ImportRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2_048)

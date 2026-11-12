from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GenerationMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    provider: str
    model: str | None
    status: str
    error_code: str | None
    requested: int
    created: int
    cached: bool
    duration_ms: int
    context_chars: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_tokens: bool
    created_at: datetime


class GenerationMetricsRead(BaseModel):
    workspace_id: str
    total_generations: int
    cached_generations: int
    cache_hit_rate: float
    average_duration_ms: int
    total_tokens: int
    average_tokens: int
    recent: list[GenerationMetricRead]

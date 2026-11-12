from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    action: str
    method: str
    path: str
    status_code: int
    duration_ms: int
    client_ip: str | None
    request_id: str | None
    created_at: datetime

from datetime import datetime

from pydantic import BaseModel, Field


class UserRead(BaseModel):
    id: str
    username: str
    display_name: str
    is_default: bool
    created_at: datetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead


class AuthStatus(BaseModel):
    auth_required: bool
    authenticated: bool
    user: UserRead | None = None
    has_users: bool

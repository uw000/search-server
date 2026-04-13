import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


VALID_ROLES = {"admin", "editor", "viewer"}
MIN_PASSWORD_LENGTH = 8


class UserCreate(BaseModel):
    username: str
    email: str | None = None
    password: str
    display_name: str | None = None
    role: str = "viewer"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다")
        if v.isdigit():
            raise ValueError("비밀번호에 문자가 포함되어야 합니다")
        if v.isalpha():
            raise ValueError("비밀번호에 숫자가 포함되어야 합니다")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"유효하지 않은 역할: {v}. 허용: {VALID_ROLES}")
        return v


class UserUpdate(BaseModel):
    email: str | None = None
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"유효하지 않은 역할: {v}. 허용: {VALID_ROLES}")
        return v


class UserResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    email: str | None
    display_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}

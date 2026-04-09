import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: str | None = None
    password: str
    display_name: str | None = None
    role: str = "viewer"


class UserUpdate(BaseModel):
    email: str | None = None
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


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

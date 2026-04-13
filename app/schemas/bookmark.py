import uuid
from datetime import datetime

from pydantic import BaseModel


class BookmarkCreate(BaseModel):
    file_id: uuid.UUID
    note: str | None = None


class BookmarkUpdate(BaseModel):
    note: str | None = None


class BookmarkResponse(BaseModel):
    user_id: uuid.UUID
    file_id: uuid.UUID
    note: str | None
    created_at: datetime
    file_name: str | None = None
    title: str | None = None

    model_config = {"from_attributes": True}

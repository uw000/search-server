import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    file_id: uuid.UUID
    file_name: str
    file_path: str
    file_size: int
    format: str
    parse_status: str
    parse_quality: float
    title: str | None = None
    author: str | None = None
    total_pages: int | None = None
    total_chunks: int = 0
    has_ocr_pages: bool = False
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[DocumentResponse]

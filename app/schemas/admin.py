from pydantic import BaseModel


class SystemStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_users: int
    parse_status_counts: dict[str, int]
    formats_counts: dict[str, int]


class ParseStatusItem(BaseModel):
    file_id: str
    file_name: str
    format: str
    parse_status: str
    parse_quality: float
    parse_error: str | None = None

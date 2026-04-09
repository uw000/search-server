from pydantic import BaseModel


class SearchResult(BaseModel):
    doc_id: str | None = None
    chunk_id: str | None = None
    title: str | None = None
    author: str | None = None
    format: str | None = None
    page_number: int | None = None
    chapter: str | None = None
    highlight: list[str] = []
    score: float | None = None
    is_ocr: bool = False


class SearchResponse(BaseModel):
    query: str
    total: int
    page: int
    size: int
    took_ms: int
    results: list[SearchResult]

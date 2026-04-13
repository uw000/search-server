from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedChunk:
    content: str
    page_number: int | None = None
    chapter: str | None = None
    section: str | None = None
    content_type: str = "text"
    is_ocr: bool = False
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.content)


@dataclass
class ParseResult:
    chunks: list[ParsedChunk] = field(default_factory=list)
    title: str | None = None
    author: str | None = None
    language: str | None = None
    total_pages: int | None = None
    has_ocr_pages: bool = False
    errors: list[str] = field(default_factory=list)


MIN_CHUNK_SIZE = 100
MAX_CHUNK_SIZE = 5000
OVERLAP_SIZE = 200
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2GB


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        ...

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        ...

    def check_file_size(self, file_path: Path) -> str | None:
        """파일 크기 검증. 초과 시 에러 메시지 반환."""
        size = file_path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            return (
                f"파일 크기 {size / (1024**3):.1f}GB가 "
                f"최대 허용 크기 {MAX_FILE_SIZE_BYTES / (1024**3):.0f}GB를 초과합니다"
            )
        return None

    def merge_small_chunks(self, chunks: list[ParsedChunk]) -> list[ParsedChunk]:
        if not chunks:
            return chunks

        merged: list[ParsedChunk] = []
        for chunk in chunks:
            if merged and chunk.char_count < MIN_CHUNK_SIZE:
                prev = merged[-1]
                merged[-1] = ParsedChunk(
                    content=prev.content + "\n" + chunk.content,
                    page_number=prev.page_number,
                    chapter=prev.chapter or chunk.chapter,
                    section=prev.section or chunk.section,
                    content_type=prev.content_type,
                    is_ocr=prev.is_ocr or chunk.is_ocr,
                )
            else:
                merged.append(chunk)
        return merged

    def split_large_chunk(self, chunk: ParsedChunk) -> list[ParsedChunk]:
        if chunk.char_count <= MAX_CHUNK_SIZE:
            return [chunk]

        parts: list[ParsedChunk] = []
        text = chunk.content
        start = 0
        while start < len(text):
            end = min(start + MAX_CHUNK_SIZE, len(text))
            parts.append(ParsedChunk(
                content=text[start:end],
                page_number=chunk.page_number,
                chapter=chunk.chapter,
                section=chunk.section,
                content_type=chunk.content_type,
                is_ocr=chunk.is_ocr,
            ))
            start = end
        return parts

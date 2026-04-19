import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings


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


# 하위 호환 alias — 신규 코드는 settings.chunk_* 를 직접 사용할 것
MIN_CHUNK_SIZE = settings.chunk_min_size
MAX_CHUNK_SIZE = settings.chunk_max_size
OVERLAP_SIZE = settings.chunk_overlap_size
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2GB


_KOR_SENTENCE_END = re.compile(r"[다요죠음임][\.!?][\s\"')\]」』]*")
_EN_SENTENCE_END = re.compile(r"[\.!?][\s\"')\]」』]*")


def _find_split_boundary(text: str, start: int, hard_end: int) -> int:
    """start ~ hard_end 구간 안에서 가장 자연스러운 경계를 찾는다.

    우선순위: 문단(\n\n) > 한국어 종결어미+구두점 > 영문 구두점 > 공백 > hard_end.
    반환값은 'end'로 사용할 인덱스 (exclusive).
    """
    if hard_end >= len(text):
        return len(text)

    segment = text[start:hard_end]

    para = segment.rfind("\n\n")
    if para >= 0 and para > (hard_end - start) // 2:
        return start + para + 2

    ko_match: re.Match[str] | None = None
    for m in _KOR_SENTENCE_END.finditer(segment):
        ko_match = m
    if ko_match and ko_match.end() > (hard_end - start) // 2:
        return start + ko_match.end()

    en_match: re.Match[str] | None = None
    for m in _EN_SENTENCE_END.finditer(segment):
        en_match = m
    if en_match and en_match.end() > (hard_end - start) // 2:
        return start + en_match.end()

    space = segment.rfind(" ")
    if space >= 0 and space > (hard_end - start) // 2:
        return start + space + 1

    return hard_end


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
        """동일 content_type 의 작은 청크를 이전 청크에 병합.

        서로 다른 타입(text / table / image_ocr) 을 섞으면 검색·하이라이트 품질이 떨어지므로
        병합 조건에 content_type 일치를 요구한다.
        """
        min_size = settings.chunk_min_size
        if not chunks:
            return chunks

        merged: list[ParsedChunk] = []
        for chunk in chunks:
            can_merge = (
                merged
                and chunk.char_count < min_size
                and merged[-1].content_type == chunk.content_type
            )
            if can_merge:
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

    def split_large_chunk(self, chunk: ParsedChunk, apply_overlap: bool = True) -> list[ParsedChunk]:
        """최대 크기 초과 시 경계 인식 분할. apply_overlap=False면 PDF처럼 페이지 단위 분할."""
        max_size = settings.chunk_max_size
        overlap = settings.chunk_overlap_size if apply_overlap else 0

        if chunk.char_count <= max_size:
            return [chunk]

        parts: list[ParsedChunk] = []
        text = chunk.content
        start = 0
        while start < len(text):
            hard_end = min(start + max_size, len(text))
            end = _find_split_boundary(text, start, hard_end)
            if end <= start:
                end = hard_end

            piece = text[start:end].strip()
            if piece:
                parts.append(ParsedChunk(
                    content=piece,
                    page_number=chunk.page_number,
                    chapter=chunk.chapter,
                    section=chunk.section,
                    content_type=chunk.content_type,
                    is_ocr=chunk.is_ocr,
                ))

            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return parts

    def chunk_long_text(
        self,
        text: str,
        page_number: int | None = None,
        chapter: str | None = None,
        section: str | None = None,
        content_type: str = "text",
        is_ocr: bool = False,
    ) -> list[ParsedChunk]:
        """텍스트를 경계 인식 + 오버랩으로 분할. 파서가 공통 사용."""
        seed = ParsedChunk(
            content=text,
            page_number=page_number,
            chapter=chapter,
            section=section,
            content_type=content_type,
            is_ocr=is_ocr,
        )
        return self.split_large_chunk(seed, apply_overlap=True)

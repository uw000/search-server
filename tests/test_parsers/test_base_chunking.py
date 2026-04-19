"""BaseParser 의 split_large_chunk / chunk_long_text 경계 인식 테스트."""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.parsers.base import BaseParser, ParsedChunk, ParseResult


class _DummyParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".dummy"]

    def parse(self, file_path: Path) -> ParseResult:  # pragma: no cover
        return ParseResult()


def test_split_under_max_returns_single() -> None:
    parser = _DummyParser()
    chunk = ParsedChunk(content="짧은 텍스트", page_number=1)
    parts = parser.split_large_chunk(chunk)
    assert len(parts) == 1
    assert parts[0].content == "짧은 텍스트"


def test_split_applies_overlap() -> None:
    parser = _DummyParser()
    # 하드 컷이 필요하도록 공백 없는 긴 문자열 + 오버랩 대상
    body = "가" * (settings.chunk_max_size * 2 + 100)
    chunk = ParsedChunk(content=body, page_number=1)

    parts = parser.split_large_chunk(chunk, apply_overlap=True)
    assert len(parts) >= 2

    total_len = sum(p.char_count for p in parts)
    # 오버랩이 적용되었다면 합친 길이가 원문보다 길어야 한다
    assert total_len > len(body)


def test_split_boundary_prefers_paragraph() -> None:
    parser = _DummyParser()
    # 두 개의 긴 문단을 \n\n 로 구분. 합이 max_size 를 초과하도록 4000자씩.
    first = ("가나다라. " * 800).strip()   # 약 4000자 (6자 * 800 - 1)
    second = ("마바사아. " * 800).strip()
    body = first + "\n\n" + second

    chunk = ParsedChunk(content=body, page_number=1)
    parts = parser.split_large_chunk(chunk, apply_overlap=True)
    assert len(parts) >= 2

    # 첫 청크는 문단 경계(\n\n) 또는 한국어 종결어미('.')에서 끝나야 한다
    first_chunk_end = parts[0].content.rstrip()
    assert first_chunk_end.endswith(".")


def test_split_no_overlap_for_pdf() -> None:
    parser = _DummyParser()
    body = "A" * (settings.chunk_max_size * 2 + 10)
    chunk = ParsedChunk(content=body, page_number=1)

    parts = parser.split_large_chunk(chunk, apply_overlap=False)
    total_len = sum(p.char_count for p in parts)
    # PDF 경로(오버랩 없음)는 합친 길이가 원본과 같아야 한다
    assert total_len == len(body)


def test_chunk_long_text_propagates_metadata() -> None:
    parser = _DummyParser()
    body = "문단 A." * 3000  # 길어서 분할됨
    parts = parser.chunk_long_text(
        body,
        page_number=7,
        chapter="Ch.2",
        section="Sec-1",
        is_ocr=True,
    )
    assert len(parts) >= 2
    for p in parts:
        assert p.page_number == 7
        assert p.chapter == "Ch.2"
        assert p.section == "Sec-1"
        assert p.is_ocr is True


def test_merge_small_chunks_combines_tiny_follower() -> None:
    parser = _DummyParser()
    first = ParsedChunk(content="A" * settings.chunk_min_size, page_number=1)
    tiny = ParsedChunk(content="B" * (settings.chunk_min_size - 10), page_number=1)
    merged = parser.merge_small_chunks([first, tiny])
    assert len(merged) == 1
    assert "A" in merged[0].content and "B" in merged[0].content

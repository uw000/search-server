from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_txt_parser_basic(tmp_path: Path) -> None:
    from app.parsers.txt_parser import TxtParser

    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello world. " * 100, encoding="utf-8")

    parser = TxtParser()
    result = parser.parse(test_file)

    assert len(result.chunks) > 0
    assert result.title == "test"
    assert all(c.content_type == "text" for c in result.chunks)


def test_txt_parser_chunking(tmp_path: Path) -> None:
    from app.parsers.txt_parser import TxtParser

    # chunk_max_size(기본 5000) 를 확실히 초과시켜 다중 청크 분할 검증
    long_text = ("문단 하나입니다. " * 400).strip() + "\n\n" + ("또 다른 문단입니다. " * 400).strip()
    test_file = tmp_path / "long.txt"
    test_file.write_text(long_text, encoding="utf-8")

    parser = TxtParser()
    result = parser.parse(test_file)

    assert len(result.chunks) >= 2


def test_txt_parser_encoding(tmp_path: Path) -> None:
    from app.parsers.txt_parser import TxtParser

    test_file = tmp_path / "korean.txt"
    test_file.write_bytes("한국어 텍스트입니다.".encode("euc-kr"))

    parser = TxtParser()
    result = parser.parse(test_file)

    assert len(result.chunks) > 0
    assert "한국어" in result.chunks[0].content


def test_txt_parser_empty_file(tmp_path: Path) -> None:
    from app.parsers.txt_parser import TxtParser

    test_file = tmp_path / "empty.txt"
    test_file.write_text("", encoding="utf-8")

    parser = TxtParser()
    result = parser.parse(test_file)

    assert len(result.chunks) == 0

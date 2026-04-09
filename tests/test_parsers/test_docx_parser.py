from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    """임시 DOCX 파일 생성."""
    from docx import Document

    doc = Document()
    doc.add_heading("Test Document", level=1)
    doc.add_paragraph("This is the introduction paragraph with enough text to be meaningful.")
    doc.add_heading("Chapter 1", level=2)
    doc.add_paragraph("Chapter 1 content. " * 20)
    doc.add_heading("Chapter 2", level=2)
    doc.add_paragraph("Chapter 2 content. " * 20)

    path = tmp_path / "test.docx"
    doc.save(str(path))
    return path


def test_docx_parser_basic(sample_docx: Path) -> None:
    from app.parsers.docx_parser import DocxParser

    parser = DocxParser()
    result = parser.parse(sample_docx)

    assert len(result.chunks) >= 2
    assert result.title is not None


def test_docx_parser_extensions() -> None:
    from app.parsers.docx_parser import DocxParser

    parser = DocxParser()
    assert ".docx" in parser.supported_extensions()

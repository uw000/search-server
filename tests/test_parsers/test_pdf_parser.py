from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """임시 텍스트 PDF 생성 (PyMuPDF 사용)."""
    import fitz

    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()

    for i in range(3):
        page = doc.new_page()
        text_point = fitz.Point(72, 72)
        page.insert_text(text_point, f"Page {i + 1} content. 한국어 텍스트 포함.")

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_pdf_parser_basic(sample_pdf: Path) -> None:
    from app.parsers.pdf_parser import PdfParser

    parser = PdfParser()
    result = parser.parse(sample_pdf)

    assert result.total_pages == 3
    assert len(result.chunks) >= 1
    assert not result.has_ocr_pages
    # 짧은 페이지는 merge_small_chunks에 의해 합쳐질 수 있음
    all_text = " ".join(c.content for c in result.chunks)
    assert "Page 1" in all_text
    assert "Page 3" in all_text


def test_pdf_parser_extensions() -> None:
    from app.parsers.pdf_parser import PdfParser

    parser = PdfParser()
    assert ".pdf" in parser.supported_extensions()


def test_is_scan_page() -> None:
    from app.parsers.pdf_parser import is_scan_page

    assert is_scan_page("short", 1)
    assert not is_scan_page("This is a long enough text with more than fifty characters in total.", 0)
    assert not is_scan_page("A" * 100, 5)

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


def _make_text_pdf_with_embedded_image(path: Path, image_size_px: int) -> None:
    """텍스트 + 지정 크기의 임베디드 이미지 1 개 포함 PDF."""
    import io

    import fitz
    from PIL import Image

    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=500)
        page.insert_text(fitz.Point(72, 72), "Body text line." * 5)
        img = Image.new("RGB", (image_size_px, image_size_px), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        # 페이지의 작은 영역에 이미지 삽입
        rect = fitz.Rect(50, 150, 250, 350)
        page.insert_image(rect, stream=buf.getvalue())
        doc.save(str(path))
    finally:
        doc.close()


def test_embedded_image_ocr_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    """기본(OFF)에서는 임베디드 이미지 경로를 건드리지 않는다."""
    from app.parsers.pdf_parser import PdfParser

    pdf = tmp_path / "text_with_img.pdf"
    _make_text_pdf_with_embedded_image(pdf, image_size_px=600)

    # ocr_image_from_bytes 가 호출되면 실패하도록 덮어쓴다. 호출 안 돼야 통과.
    import app.parsers.ocr_processor as ocr_mod

    def _boom(_b: bytes, lang: str = "kor+eng") -> str:
        raise AssertionError("OCR must not run when embedded image OCR is disabled")

    monkeypatch.setattr(ocr_mod, "ocr_image_from_bytes", _boom)

    parser = PdfParser()
    result = parser.parse(pdf)
    # 텍스트 페이지는 정상 처리
    assert any(c.content_type == "text" for c in result.chunks)
    # 임베디드 이미지 OCR 청크는 없어야 함
    assert not any(c.content_type == "image_ocr" for c in result.chunks)


def test_embedded_image_ocr_skips_small_images(tmp_path: Path, monkeypatch) -> None:
    """min_width/min_height 미만 이미지는 OCR 하지 않는다."""
    from app.config import settings
    from app.parsers.pdf_parser import PdfParser

    pdf = tmp_path / "text_with_small_img.pdf"
    _make_text_pdf_with_embedded_image(pdf, image_size_px=100)  # 300px 미만

    monkeypatch.setattr(settings, "pdf_embedded_image_ocr_enabled", True)

    import app.parsers.ocr_processor as ocr_mod

    def _boom(_b: bytes, lang: str = "kor+eng") -> str:
        raise AssertionError("OCR must not run for sub-threshold image")

    monkeypatch.setattr(ocr_mod, "ocr_image_from_bytes", _boom)

    parser = PdfParser()
    result = parser.parse(pdf)
    assert not any(c.content_type == "image_ocr" for c in result.chunks)


def test_embedded_image_ocr_runs_when_enabled(tmp_path: Path, monkeypatch) -> None:
    """크기 조건 + ON 플래그가 만족되면 OCR 을 호출하고 결과가 별도 청크로 저장된다."""
    from app.config import settings
    from app.parsers.pdf_parser import PdfParser

    pdf = tmp_path / "text_with_big_img.pdf"
    _make_text_pdf_with_embedded_image(pdf, image_size_px=600)

    monkeypatch.setattr(settings, "pdf_embedded_image_ocr_enabled", True)

    import app.parsers.ocr_processor as ocr_mod

    calls = {"n": 0}

    def _fake_ocr(_b: bytes, lang: str = "kor+eng") -> str:
        calls["n"] += 1
        return "EXTRACTED FROM IMAGE"

    monkeypatch.setattr(ocr_mod, "ocr_image_from_bytes", _fake_ocr)

    parser = PdfParser()
    result = parser.parse(pdf)

    assert calls["n"] >= 1
    image_chunks = [c for c in result.chunks if c.content_type == "image_ocr"]
    assert image_chunks, "expected at least one image_ocr chunk"
    assert any("EXTRACTED FROM IMAGE" in c.content for c in image_chunks)
    assert result.has_ocr_pages is True

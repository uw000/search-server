"""pdf_preprocessor 단위 테스트."""
from __future__ import annotations

import io
from pathlib import Path

import fitz
import pytest
from PIL import Image


def _make_scanned_pdf(path: Path, dpi: int, pages: int = 2, page_in_inches: tuple[float, float] = (4.0, 5.0)) -> None:
    """지정 DPI 로 full-page 이미지 PDF 를 생성 (스캔본 시뮬레이션)."""
    w_in, h_in = page_in_inches
    w_pt = w_in * 72.0
    h_pt = h_in * 72.0
    w_px = int(w_in * dpi)
    h_px = int(h_in * dpi)

    doc = fitz.open()
    try:
        for i in range(pages):
            # 구분 가능한 텍스트가 포함된 흰 바탕 이미지
            img = Image.new("RGB", (w_px, h_px), color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            page = doc.new_page(width=w_pt, height=h_pt)
            page.insert_image(page.rect, stream=buf.getvalue())
        doc.save(str(path))
    finally:
        doc.close()


def _make_text_pdf(path: Path, pages: int = 2) -> None:
    """텍스트 기반 PDF (임베디드 이미지 없음)."""
    doc = fitz.open()
    try:
        for i in range(pages):
            page = doc.new_page()
            page.insert_text(fitz.Point(72, 72), f"Page {i + 1} text content")
        doc.save(str(path))
    finally:
        doc.close()


def test_detect_dpi_on_600dpi_scanned_pdf(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import detect_dpi

    pdf = tmp_path / "scan_600.pdf"
    _make_scanned_pdf(pdf, dpi=600, pages=2)

    detected = detect_dpi(pdf, sample=2)
    assert detected is not None
    # 정확히 600 이 아닐 수 있으나 오차 5% 이내여야 함
    assert abs(detected - 600) <= 30


def test_detect_dpi_on_300dpi_scanned_pdf(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import detect_dpi

    pdf = tmp_path / "scan_300.pdf"
    _make_scanned_pdf(pdf, dpi=300, pages=2)

    detected = detect_dpi(pdf, sample=2)
    assert detected is not None
    assert abs(detected - 300) <= 15


def test_detect_dpi_on_text_pdf_returns_none(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import detect_dpi

    pdf = tmp_path / "text.pdf"
    _make_text_pdf(pdf, pages=3)

    assert detect_dpi(pdf, sample=3) is None


def test_detect_dpi_samples_fewer_than_total(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import detect_dpi

    pdf = tmp_path / "scan_5pages.pdf"
    _make_scanned_pdf(pdf, dpi=450, pages=5)

    detected = detect_dpi(pdf, sample=2)
    assert detected is not None
    assert abs(detected - 450) <= 25


def test_archive_original_preserves_source(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import archive_original

    originals = tmp_path / "originals"
    src = tmp_path / "book.pdf"
    src.write_bytes(b"fake pdf bytes")

    archived = archive_original(src, originals)

    assert src.exists()              # 원본은 그대로 남음 (copy)
    assert archived.exists()
    assert archived.read_bytes() == b"fake pdf bytes"
    assert archived.parent == originals


def test_archive_original_handles_name_collision(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import archive_original

    originals = tmp_path / "originals"
    originals.mkdir()
    (originals / "book.pdf").write_bytes(b"existing")

    src = tmp_path / "book.pdf"
    src.write_bytes(b"new content")

    archived = archive_original(src, originals)
    assert archived.name != "book.pdf"
    assert archived.stem.startswith("book__")
    assert archived.read_bytes() == b"new content"


def test_downscale_reduces_file_size(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import downscale_pdf

    src = tmp_path / "hi.pdf"
    _make_scanned_pdf(src, dpi=600, pages=2, page_in_inches=(4.0, 5.0))
    src_size = src.stat().st_size

    dst = tmp_path / "lo.pdf"
    downscale_pdf(src, dst, target_dpi=150, jpeg_quality=75)

    assert dst.exists()
    assert dst.stat().st_size < src_size


def test_downscale_preserves_page_count_and_dimensions(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import downscale_pdf

    src = tmp_path / "src.pdf"
    _make_scanned_pdf(src, dpi=400, pages=3, page_in_inches=(4.0, 5.0))

    dst = tmp_path / "dst.pdf"
    downscale_pdf(src, dst, target_dpi=200)

    doc = fitz.open(str(dst))
    try:
        assert len(doc) == 3
        # 페이지 크기(points)는 보존되어야 한다
        assert abs(doc[0].rect.width - 4.0 * 72) < 1
        assert abs(doc[0].rect.height - 5.0 * 72) < 1
    finally:
        doc.close()


def test_preprocess_skips_low_dpi(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import preprocess_pdf

    originals = tmp_path / "originals"
    pdf = tmp_path / "low.pdf"
    _make_scanned_pdf(pdf, dpi=200, pages=2)
    original_bytes = pdf.read_bytes()

    result = preprocess_pdf(pdf, originals, target_dpi=300, sample_pages=2)

    assert result.downscaled is False
    assert result.path == pdf
    assert result.original_archive is None
    # 작업 파일 미변경
    assert pdf.read_bytes() == original_bytes
    # 아카이브 디렉토리도 생성되지 않았어야 한다
    assert not originals.exists() or not any(originals.iterdir())


def test_preprocess_skips_text_pdf(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import preprocess_pdf

    originals = tmp_path / "originals"
    pdf = tmp_path / "text.pdf"
    _make_text_pdf(pdf, pages=2)

    result = preprocess_pdf(pdf, originals, target_dpi=300, sample_pages=2)

    assert result.downscaled is False
    assert result.detected_dpi is None


def test_preprocess_downscales_and_archives(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import detect_dpi, preprocess_pdf

    originals = tmp_path / "originals"
    pdf = tmp_path / "hi.pdf"
    _make_scanned_pdf(pdf, dpi=600, pages=2, page_in_inches=(4.0, 5.0))
    hi_size = pdf.stat().st_size

    result = preprocess_pdf(
        pdf,
        originals,
        target_dpi=300,
        sample_pages=2,
        jpeg_quality=80,
    )

    assert result.downscaled is True
    assert result.detected_dpi is not None
    assert result.detected_dpi >= 500

    # 아카이브에 원본 보존
    assert result.original_archive is not None
    assert result.original_archive.exists()
    assert result.original_archive.stat().st_size == hi_size

    # 작업 파일은 다운스케일된 버전으로 교체
    assert pdf.exists()
    assert pdf.stat().st_size < hi_size

    # 교체된 파일의 DPI 가 목표치 근처인지 재측정
    new_dpi = detect_dpi(pdf, sample=2)
    assert new_dpi is not None
    assert abs(new_dpi - 300) <= 30


def test_preprocess_disabled_flag(tmp_path: Path) -> None:
    from app.parsers.pdf_preprocessor import preprocess_pdf

    originals = tmp_path / "originals"
    pdf = tmp_path / "hi.pdf"
    _make_scanned_pdf(pdf, dpi=600, pages=1, page_in_inches=(3.0, 3.0))
    original_size = pdf.stat().st_size

    result = preprocess_pdf(
        pdf,
        originals,
        target_dpi=300,
        sample_pages=1,
        enabled=False,
    )
    assert result.downscaled is False
    # enabled=False 면 DPI 감지도 건너뛴다
    assert result.detected_dpi is None
    # 파일/아카이브 모두 손대지 않음
    assert pdf.stat().st_size == original_size
    assert not originals.exists() or not any(originals.iterdir())

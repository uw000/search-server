"""PDF 전처리: DPI 감지 → 고해상도 스캔본 다운스케일 + 원본 아카이빙.

사용자는 보통 600 DPI 로 스캔된 PDF 를 투입하지만, 한국어 단행본 OCR 은
300 DPI 대에서 인식률이 가장 좋고 용량도 1/4 로 줄어든다.

이 모듈은 파서 호출 직전 Celery parse_task 에서 호출된다.

전체 흐름:
  1. ``detect_dpi`` — 샘플 페이지에서 임베디드 이미지의 DPI 를 계산해 중앙값 반환.
  2. DPI 가 문턱값(``settings.max_dpi``) 이하이면 건너뜀.
  3. 초과 시: 원본을 ``documents_originals_root`` 로 **복사 보존** 후,
     작업 경로에는 다운스케일된 PDF 로 **원자적 교체**.
"""
from __future__ import annotations

import io
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class PreprocessResult:
    path: Path                     # 이후 파서가 열어야 할 경로
    downscaled: bool               # 실제로 다운스케일이 수행되었는가
    detected_dpi: int | None       # 중앙값 DPI (감지 불가면 None)
    original_archive: Path | None  # 원본 보존 경로 (다운스케일 시에만)


def detect_dpi(pdf_path: Path, sample: int = 3) -> int | None:
    """샘플 페이지의 임베디드 이미지에서 DPI 중앙값을 추정.

    텍스트 기반 PDF(임베디드 이미지 없음) 또는 빈 PDF 는 None.
    """
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    if total == 0:
        doc.close()
        return None

    if sample >= total:
        indices: list[int] = list(range(total))
    else:
        # 고르게 분포된 샘플 인덱스
        indices = [int(i * total / sample) for i in range(sample)]

    per_page_dpis: list[float] = []
    for i in indices:
        page = doc[i]
        w_pt = float(page.rect.width)
        if w_pt <= 0:
            continue
        page_max_dpi = 0.0
        for img in page.get_images(full=True):
            # (xref, smask, width, height, bpc, colorspace, alt, name, filter, invoker)
            img_w = float(img[2])
            if img_w <= 0:
                continue
            dpi = img_w * 72.0 / w_pt
            if dpi > page_max_dpi:
                page_max_dpi = dpi
        if page_max_dpi > 0:
            per_page_dpis.append(page_max_dpi)

    doc.close()

    if not per_page_dpis:
        return None
    per_page_dpis.sort()
    median = per_page_dpis[len(per_page_dpis) // 2]
    return int(round(median))


def _pixmap_to_jpeg_bytes(pix: fitz.Pixmap, quality: int) -> bytes:
    """PIL 을 경유해 Pixmap → JPEG. PyMuPDF 버전 별 API 차이를 회피."""
    mode = "RGBA" if pix.alpha else "RGB"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if mode == "RGBA":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def downscale_pdf(src: Path, dst: Path, target_dpi: int = 300, jpeg_quality: int = 85) -> None:
    """각 페이지를 target_dpi 로 래스터화한 이미지로 재구성.

    주의: 모든 페이지가 이미지로 대체되므로 **텍스트 레이어는 사라진다**.
    텍스트 기반 PDF 에 호출해서는 안 된다 (호출측이 DPI 판정 후 스캔본일 때만 호출).
    """
    src_doc = fitz.open(str(src))
    dst_doc = fitz.open()
    try:
        zoom = target_dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for page in src_doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            jpeg = _pixmap_to_jpeg_bytes(pix, quality=jpeg_quality)
            new_page = dst_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=jpeg)
        dst_doc.save(str(dst), garbage=4, deflate=True)
    finally:
        src_doc.close()
        dst_doc.close()


def archive_original(src: Path, originals_root: Path) -> Path:
    """원본을 ``originals_root`` 로 복사 보존(원본은 삭제하지 않음).

    파일명 충돌 시 short-uuid 접미사를 붙여 회피.
    """
    originals_root.mkdir(parents=True, exist_ok=True)
    dst = originals_root / src.name
    if dst.exists():
        dst = originals_root / f"{src.stem}__{uuid.uuid4().hex[:8]}{src.suffix}"
    shutil.copy2(src, dst)
    return dst


def preprocess_pdf(
    pdf_path: Path,
    originals_root: Path,
    target_dpi: int = 300,
    sample_pages: int = 3,
    jpeg_quality: int = 85,
    enabled: bool = True,
) -> PreprocessResult:
    """파서 호출 직전의 PDF 전처리 오케스트레이션.

    ``enabled=False`` 이거나 DPI 가 문턱값 이하면 입력 경로를 그대로 돌려준다.
    """
    if not enabled:
        return PreprocessResult(path=pdf_path, downscaled=False, detected_dpi=None, original_archive=None)

    dpi = detect_dpi(pdf_path, sample=sample_pages)
    if dpi is None or dpi <= target_dpi:
        return PreprocessResult(path=pdf_path, downscaled=False, detected_dpi=dpi, original_archive=None)

    archived = archive_original(pdf_path, originals_root)
    tmp = pdf_path.with_suffix(pdf_path.suffix + ".tmp")
    try:
        downscale_pdf(archived, tmp, target_dpi=target_dpi, jpeg_quality=jpeg_quality)
        tmp.replace(pdf_path)
    except Exception:
        # 원본은 archived 에 보존되어 있고, 작업 파일도 손대지 않음.
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise

    logger.info(
        "PDF downscaled: %s (detected %d dpi → %d dpi, archive=%s)",
        pdf_path, dpi, target_dpi, archived,
    )
    return PreprocessResult(
        path=pdf_path,
        downscaled=True,
        detected_dpi=dpi,
        original_archive=archived,
    )

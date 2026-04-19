"""OCR 처리 — 엔진 전략 패턴.

두 개의 엔진을 제공한다:
  - SuryaEngine    : GPU/MPS/CPU 지원. 한/영 혼용 인식률 Tesseract 대비 월등.
                     ``surya-ocr`` + ``torch`` 가 필요하며 부팅 시 모델 로드(수백 MB).
  - TesseractEngine: 시스템 ``tesseract`` 바이너리에 의존. 가볍지만 정확도 낮음.

선택은 ``settings.ocr_engine`` 으로 결정:
  auto      → surya import 가능하면 Surya, 실패 시 Tesseract fallback
  surya     → Surya 강제 (import 실패 시 RuntimeError)
  tesseract → Tesseract 강제

이 모듈의 공개 함수 시그니처는 변경하지 않아서 기존 호출부 수정이 필요 없다.
"""
from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Protocol

from PIL import Image

from app.config import settings
from app.parsers.text_cleaner import normalize_linebreaks

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 엔진 인터페이스
# ─────────────────────────────────────────────────────────────


class OCREngine(Protocol):
    name: str

    def ocr_image_from_bytes(self, image_bytes: bytes, lang: str = "kor+eng") -> str: ...
    def ocr_image(self, image_path: Path, lang: str = "kor+eng") -> str: ...


def _detect_device() -> str:
    """PyTorch 가설 치되어 있을 때 CUDA > MPS > CPU 순으로 탐지."""
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# ─────────────────────────────────────────────────────────────
# Tesseract 엔진 (시스템 tesseract 바이너리 경유)
# ─────────────────────────────────────────────────────────────


class TesseractEngine:
    name = "tesseract"

    def ocr_image_from_bytes(self, image_bytes: bytes, lang: str = "kor+eng") -> str:
        import pytesseract

        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, lang=lang)
        return normalize_linebreaks(text)

    def ocr_image(self, image_path: Path, lang: str = "kor+eng") -> str:
        import pytesseract

        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang=lang)
        return normalize_linebreaks(text)


# ─────────────────────────────────────────────────────────────
# Surya 엔진 (GPU/MPS/CPU 지원)
# ─────────────────────────────────────────────────────────────


class SuryaEngine:
    """Surya 모델은 처음 호출 시에 로드된다 (부팅 지연 회피).

    주의: Surya 의 내부 API 는 버전별 차이가 크다. 본 래퍼는 0.14+ 계열에서 동작하도록 작성되어 있고,
    `recognition.RecognitionPredictor` / `detection.DetectionPredictor` 를 사용한다.
    버전 차이로 import 실패 시 get_ocr_engine() 이 Tesseract 로 fallback 한다.
    """

    name = "surya"

    _det = None
    _rec = None
    _load_lock = Lock()

    def _ensure_loaded(self) -> None:
        if SuryaEngine._rec is not None:
            return
        with SuryaEngine._load_lock:
            if SuryaEngine._rec is not None:
                return

            # 디바이스 선택: auto 면 자동 탐지, 그 외엔 명시값 사용
            device = settings.surya_device
            if device == "auto":
                device = _detect_device()
            # Surya 는 TORCH_DEVICE env var 로 디바이스를 판단한다
            os.environ["TORCH_DEVICE"] = device

            logger.info("Loading Surya predictors on device=%s", device)
            from surya.detection import DetectionPredictor
            from surya.recognition import RecognitionPredictor

            SuryaEngine._det = DetectionPredictor()
            SuryaEngine._rec = RecognitionPredictor()

    def _run_ocr(self, pil_image: Image.Image) -> str:
        self._ensure_loaded()
        img = pil_image.convert("RGB")
        # Surya API: rec_predictor([images], [languages_per_image], det_predictor)
        predictions = SuryaEngine._rec(
            [img],
            [settings.surya_langs],
            SuryaEngine._det,
        )
        if not predictions:
            return ""
        result = predictions[0]
        lines: list[str] = []
        for line in getattr(result, "text_lines", []) or []:
            text = getattr(line, "text", "") or ""
            if text:
                lines.append(text)
        return normalize_linebreaks("\n".join(lines))

    def ocr_image_from_bytes(self, image_bytes: bytes, lang: str = "kor+eng") -> str:
        image = Image.open(BytesIO(image_bytes))
        return self._run_ocr(image)

    def ocr_image(self, image_path: Path, lang: str = "kor+eng") -> str:
        image = Image.open(image_path)
        return self._run_ocr(image)


# ─────────────────────────────────────────────────────────────
# 엔진 선택 및 캐싱
# ─────────────────────────────────────────────────────────────


_engine_cache: dict[str, OCREngine] = {}
_cache_lock = Lock()


def _is_surya_importable() -> bool:
    """Surya 의 실제 Predictor 클래스까지 import 가능해야 '사용 가능' 으로 간주.

    `import surya` 자체는 성공하더라도 내부 의존성(transformers 버전 등) 불일치로
    predictor 클래스 로드가 실패하는 경우가 있어서 얕은 체크는 위험하다.
    """
    try:
        import torch  # noqa: F401
        from surya.detection import DetectionPredictor  # noqa: F401
        from surya.recognition import RecognitionPredictor  # noqa: F401
        return True
    except Exception as e:  # ImportError, RuntimeError, transformers 호환성 에러 등
        logger.debug("Surya import check failed: %s", e)
        return False


def _resolve_engine_name() -> str:
    choice = settings.ocr_engine
    if choice == "auto":
        return "surya" if _is_surya_importable() else "tesseract"
    if choice == "surya" and not _is_surya_importable():
        logger.warning("ocr_engine=surya 로 설정되었으나 import 실패 → tesseract 로 fallback")
        return "tesseract"
    return choice


def get_ocr_engine() -> OCREngine:
    name = _resolve_engine_name()
    with _cache_lock:
        eng = _engine_cache.get(name)
        if eng is not None:
            return eng
        if name == "surya":
            eng = SuryaEngine()
        else:
            eng = TesseractEngine()
        _engine_cache[name] = eng
        return eng


def reset_engine_cache() -> None:
    """테스트용: 캐시된 엔진 인스턴스를 초기화."""
    with _cache_lock:
        _engine_cache.clear()


# ─────────────────────────────────────────────────────────────
# 기존 공개 API (하위 호환 유지)
# ─────────────────────────────────────────────────────────────


def ocr_image(image_path: Path, lang: str = "kor+eng") -> str:
    return get_ocr_engine().ocr_image(image_path, lang=lang)


def ocr_image_from_bytes(image_bytes: bytes, lang: str = "kor+eng") -> str:
    return get_ocr_engine().ocr_image_from_bytes(image_bytes, lang=lang)


def ocr_pdf_page(pdf_path: Path, page_number: int, lang: str = "kor+eng", dpi: int = 300) -> str:
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_number - 1]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        image_bytes = pix.tobytes("png")
    finally:
        doc.close()

    return ocr_image_from_bytes(image_bytes, lang=lang)

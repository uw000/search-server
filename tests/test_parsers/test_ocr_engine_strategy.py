"""OCR 엔진 선택/캐싱 전략 테스트 — 실제 Surya 설치 없이 모킹으로 검증.

검증 포인트:
  1. settings.ocr_engine="tesseract" 면 무조건 Tesseract
  2. settings.ocr_engine="surya" + import 실패 시 Tesseract 로 fallback + 경고
  3. settings.ocr_engine="auto" + Surya 사용 가능 → Surya 선택
  4. settings.ocr_engine="auto" + Surya 없음 → Tesseract
  5. 엔진 인스턴스는 캐싱된다
  6. _detect_device() — torch 없으면 cpu, CUDA 있으면 cuda 등
"""
from __future__ import annotations

import pytest

import app.parsers.ocr_processor as ocr_mod


@pytest.fixture(autouse=True)
def _reset_cache():
    ocr_mod.reset_engine_cache()
    yield
    ocr_mod.reset_engine_cache()


def test_tesseract_forced_selection(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod.settings, "ocr_engine", "tesseract")
    eng = ocr_mod.get_ocr_engine()
    assert eng.name == "tesseract"


def test_surya_forced_but_missing_falls_back_to_tesseract(monkeypatch, caplog) -> None:
    monkeypatch.setattr(ocr_mod.settings, "ocr_engine", "surya")
    monkeypatch.setattr(ocr_mod, "_is_surya_importable", lambda: False)

    with caplog.at_level("WARNING"):
        eng = ocr_mod.get_ocr_engine()
    assert eng.name == "tesseract"
    assert any("fallback" in rec.message.lower() for rec in caplog.records)


def test_auto_picks_surya_when_available(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod.settings, "ocr_engine", "auto")
    monkeypatch.setattr(ocr_mod, "_is_surya_importable", lambda: True)

    eng = ocr_mod.get_ocr_engine()
    assert eng.name == "surya"


def test_auto_picks_tesseract_when_surya_missing(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod.settings, "ocr_engine", "auto")
    monkeypatch.setattr(ocr_mod, "_is_surya_importable", lambda: False)

    eng = ocr_mod.get_ocr_engine()
    assert eng.name == "tesseract"


def test_engine_instance_is_cached(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod.settings, "ocr_engine", "tesseract")
    a = ocr_mod.get_ocr_engine()
    b = ocr_mod.get_ocr_engine()
    assert a is b


def test_reset_cache_produces_fresh_instance(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod.settings, "ocr_engine", "tesseract")
    a = ocr_mod.get_ocr_engine()
    ocr_mod.reset_engine_cache()
    b = ocr_mod.get_ocr_engine()
    assert a is not b


def test_detect_device_no_torch(monkeypatch) -> None:
    # torch import 자체를 실패시킨다
    import builtins

    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("no torch in this env")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ocr_mod._detect_device() == "cpu"


def test_detect_device_with_cuda(monkeypatch) -> None:
    """torch 가 있고 CUDA 가 보이면 cuda 반환."""
    import sys
    import types

    fake_torch = types.ModuleType("torch")

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return True

    fake_torch.cuda = _Cuda
    fake_backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    fake_torch.backends = fake_backends

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert ocr_mod._detect_device() == "cuda"


def test_detect_device_falls_back_to_mps(monkeypatch) -> None:
    import sys
    import types

    fake_torch = types.ModuleType("torch")

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch.cuda = _Cuda
    fake_backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: True))
    fake_torch.backends = fake_backends

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert ocr_mod._detect_device() == "mps"


def test_detect_device_cpu_when_nothing_available(monkeypatch) -> None:
    import sys
    import types

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    fake_torch.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False)
    )

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert ocr_mod._detect_device() == "cpu"


def test_public_api_routes_through_engine(monkeypatch) -> None:
    """ocr_image_from_bytes 가 선택된 엔진의 메서드를 호출해야 한다."""
    monkeypatch.setattr(ocr_mod.settings, "ocr_engine", "tesseract")

    calls = {"n": 0}

    class FakeEngine:
        name = "fake"

        def ocr_image_from_bytes(self, data, lang="kor+eng"):
            calls["n"] += 1
            return f"FAKE[{len(data)}b,lang={lang}]"

        def ocr_image(self, p, lang="kor+eng"):
            calls["n"] += 1
            return f"FAKE[{p},lang={lang}]"

    monkeypatch.setattr(ocr_mod, "get_ocr_engine", lambda: FakeEngine())

    out = ocr_mod.ocr_image_from_bytes(b"\x00\x01\x02", lang="eng")
    assert "FAKE[3b" in out
    assert calls["n"] == 1

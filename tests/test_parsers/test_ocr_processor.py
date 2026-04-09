from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.mark.skip(reason="Tesseract not available in CI/dev without Docker")
def test_ocr_image(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    from app.parsers.ocr_processor import ocr_image

    img = Image.new("RGB", (200, 50), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Hello World", fill="black")
    img_path = tmp_path / "test.png"
    img.save(str(img_path))

    text = ocr_image(img_path, lang="eng")
    assert "Hello" in text or "hello" in text.lower()

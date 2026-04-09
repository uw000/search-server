from pathlib import Path

import pytesseract
from PIL import Image


def ocr_image(image_path: Path, lang: str = "kor+eng") -> str:
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image, lang=lang)
    return text.strip()


def ocr_image_from_bytes(image_bytes: bytes, lang: str = "kor+eng") -> str:
    from io import BytesIO

    image = Image.open(BytesIO(image_bytes))
    text = pytesseract.image_to_string(image, lang=lang)
    return text.strip()


def ocr_pdf_page(pdf_path: Path, page_number: int, lang: str = "kor+eng", dpi: int = 300) -> str:
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]

    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    image_bytes = pix.tobytes("png")
    doc.close()

    return ocr_image_from_bytes(image_bytes, lang=lang)

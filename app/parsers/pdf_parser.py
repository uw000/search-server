from pathlib import Path

import fitz  # PyMuPDF

from app.parsers.base import BaseParser, ParsedChunk, ParseResult


def is_scan_page(page_text: str, page_images: int) -> bool:
    return len(page_text.strip()) < 50 and page_images >= 1


class PdfParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()

        size_error = self.check_file_size(file_path)
        if size_error:
            result.errors.append(size_error)
            return result

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            result.errors.append(f"Failed to open PDF: {e}")
            return result

        result.title = doc.metadata.get("title") or file_path.stem
        result.author = doc.metadata.get("author")
        result.total_pages = len(doc)

        ocr_pages: list[int] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            image_count = len(page.get_images(full=True))

            if is_scan_page(text, image_count):
                ocr_pages.append(page_num + 1)
                result.chunks.append(ParsedChunk(
                    content=text.strip() if text.strip() else f"[Scan page {page_num + 1} - OCR required]",
                    page_number=page_num + 1,
                    content_type="image_ocr",
                    is_ocr=True,
                ))
            elif text.strip():
                for chunk in self.split_large_chunk(ParsedChunk(
                    content=text.strip(),
                    page_number=page_num + 1,
                    content_type="text",
                )):
                    result.chunks.append(chunk)

        doc.close()

        if ocr_pages:
            result.has_ocr_pages = True

        result.chunks = self.merge_small_chunks(result.chunks)
        return result

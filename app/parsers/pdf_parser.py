from pathlib import Path

import fitz  # PyMuPDF

from app.config import settings
from app.parsers.base import BaseParser, ParsedChunk, ParseResult
from app.parsers.text_cleaner import (
    clean_text,
    remove_repeated_headers_footers,
)


def is_scan_page(page_text: str, page_images: int) -> bool:
    return len(page_text.strip()) < 50 and page_images >= 1


def _ocr_embedded_images_on_page(
    doc: fitz.Document,
    page_num_zero_indexed: int,
    min_width: int,
    min_height: int,
) -> list[str]:
    """페이지 내 임베디드 이미지 중 최소 크기를 넘는 것들에 OCR. PyMuPDF 예외는 조용히 패스."""
    from app.parsers.ocr_processor import ocr_image_from_bytes

    page = doc[page_num_zero_indexed]
    results: list[str] = []
    for img in page.get_images(full=True):
        xref = img[0]
        width, height = img[2], img[3]
        if width < min_width or height < min_height:
            continue
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n >= 5:  # CMYK 또는 알파 포함 다채널 → RGB 변환
                pix = fitz.Pixmap(fitz.csRGB, pix)
            img_bytes = pix.tobytes("png")
            pix = None  # 메모리 해제 힌트
        except Exception:
            continue
        try:
            text = ocr_image_from_bytes(img_bytes)
        except Exception:
            continue
        if text and text.strip():
            results.append(text)
    return results


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

        try:
            result.title = doc.metadata.get("title") or file_path.stem
            result.author = doc.metadata.get("author")
            result.total_pages = len(doc)

            raw_pages: list[str] = []
            image_counts: list[int] = []
            embedded_image_ocr: dict[int, list[str]] = {}

            for page_num in range(len(doc)):
                page = doc[page_num]
                raw_pages.append(page.get_text("text"))
                image_counts.append(len(page.get_images(full=True)))

            # 이미지 OCR 은 doc 가 열려 있어야 xref 로 Pixmap 을 꺼낼 수 있음
            if settings.pdf_embedded_image_ocr_enabled:
                for page_num in range(len(doc)):
                    page_text = raw_pages[page_num]
                    image_count = image_counts[page_num]
                    # 스캔 페이지는 기존 OCR 경로에서 전체 페이지 OCR 로 처리하므로 중복 회피
                    if is_scan_page(page_text, image_count):
                        continue
                    if image_count == 0:
                        continue
                    texts = _ocr_embedded_images_on_page(
                        doc,
                        page_num,
                        min_width=settings.pdf_embedded_image_min_width_px,
                        min_height=settings.pdf_embedded_image_min_height_px,
                    )
                    if texts:
                        embedded_image_ocr[page_num + 1] = texts
        finally:
            doc.close()

        # 1) 머리글/바닥글 제거는 정제 전(원본 줄바꿈 유지 상태)에서 수행
        deheaded = remove_repeated_headers_footers(raw_pages)

        # 2) 페이지별 줄바꿈/하이픈/페이지번호 정제
        cleaned_pages = [clean_text(p) for p in deheaded]

        ocr_pages: list[int] = []
        for page_num, (text, image_count) in enumerate(zip(cleaned_pages, image_counts), start=1):
            if is_scan_page(text, image_count):
                ocr_pages.append(page_num)
                result.chunks.append(ParsedChunk(
                    content=text if text.strip() else f"[Scan page {page_num} - OCR required]",
                    page_number=page_num,
                    content_type="image_ocr",
                    is_ocr=True,
                ))
            elif text.strip():
                # PDF 는 페이지 단위 보존이 중요하므로 오버랩 미적용
                for chunk in self.split_large_chunk(
                    ParsedChunk(
                        content=text,
                        page_number=page_num,
                        content_type="text",
                    ),
                    apply_overlap=False,
                ):
                    result.chunks.append(chunk)

        # 임베디드 이미지 OCR 결과를 별도 청크로 추가
        for page_num, texts in sorted(embedded_image_ocr.items()):
            combined = clean_text("\n\n".join(texts), drop_page_numbers=False)
            if not combined.strip():
                continue
            result.chunks.append(ParsedChunk(
                content=combined,
                page_number=page_num,
                content_type="image_ocr",
                is_ocr=True,
            ))

        if ocr_pages or embedded_image_ocr:
            result.has_ocr_pages = True

        result.chunks = self.merge_small_chunks(result.chunks)
        return result

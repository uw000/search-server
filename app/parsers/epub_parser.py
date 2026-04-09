from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from app.parsers.base import OVERLAP_SIZE, BaseParser, ParsedChunk, ParseResult


class EpubParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".epub"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()

        try:
            book = epub.read_epub(str(file_path), options={"ignore_ncx": True})
        except Exception as e:
            result.errors.append(f"Failed to open EPUB: {e}")
            return result

        result.title = book.get_metadata("DC", "title")
        if result.title:
            result.title = result.title[0][0]
        else:
            result.title = file_path.stem

        authors = book.get_metadata("DC", "creator")
        if authors:
            result.author = authors[0][0]

        language = book.get_metadata("DC", "language")
        if language:
            result.language = language[0][0]

        chapter_num = 0
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator="\n", strip=True)

            if not text.strip():
                continue

            chapter_num += 1
            chapter_title = None
            heading = soup.find(["h1", "h2", "h3"])
            if heading:
                chapter_title = heading.get_text(strip=True)

            chunks = self._chunk_with_overlap(text, chapter_num, chapter_title)
            result.chunks.extend(chunks)

        result.chunks = self.merge_small_chunks(result.chunks)
        result.total_pages = chapter_num
        return result

    def _chunk_with_overlap(
        self, text: str, chapter_num: int, chapter_title: str | None
    ) -> list[ParsedChunk]:
        from app.parsers.base import MAX_CHUNK_SIZE

        chunks: list[ParsedChunk] = []

        if len(text) <= MAX_CHUNK_SIZE:
            chunks.append(ParsedChunk(
                content=text,
                page_number=chapter_num,
                chapter=chapter_title,
                content_type="text",
            ))
            return chunks

        start = 0
        while start < len(text):
            end = min(start + MAX_CHUNK_SIZE, len(text))
            chunk_text = text[start:end]

            if chunk_text.strip():
                chunks.append(ParsedChunk(
                    content=chunk_text,
                    page_number=chapter_num,
                    chapter=chapter_title,
                    content_type="text",
                ))

            if end >= len(text):
                break
            start = end - OVERLAP_SIZE

        return chunks

from pathlib import Path

import chardet

from app.parsers.base import BaseParser, ParseResult
from app.parsers.text_cleaner import clean_text


class TxtParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".txt"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()

        size_error = self.check_file_size(file_path)
        if size_error:
            result.errors.append(size_error)
            return result

        try:
            raw = file_path.read_bytes()
            detected = chardet.detect(raw)
            encoding = detected.get("encoding") or "utf-8"
            text = raw.decode(encoding, errors="replace")
        except Exception as e:
            result.errors.append(f"Failed to read file: {e}")
            return result

        result.title = file_path.stem
        text = clean_text(text, drop_page_numbers=False)

        if not text.strip():
            return result

        chunks = self.chunk_long_text(text, page_number=1, content_type="text")
        chunks = self.merge_small_chunks(chunks)
        result.chunks = chunks
        result.total_pages = len(chunks)
        return result

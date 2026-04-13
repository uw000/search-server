from pathlib import Path

import chardet

from app.parsers.base import OVERLAP_SIZE, BaseParser, ParsedChunk, ParseResult

CHUNK_SIZE = 2000


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

        chunks: list[ParsedChunk] = []
        start = 0
        chunk_num = 0

        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            chunk_text = text[start:end]

            if chunk_text.strip():
                chunk_num += 1
                chunks.append(ParsedChunk(
                    content=chunk_text,
                    page_number=chunk_num,
                    content_type="text",
                ))

            if end >= len(text):
                break
            start = end - OVERLAP_SIZE

        chunks = self.merge_small_chunks(chunks)
        result.chunks = chunks
        result.total_pages = len(chunks)
        return result

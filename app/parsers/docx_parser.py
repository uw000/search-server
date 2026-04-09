from pathlib import Path

from docx import Document

from app.parsers.base import OVERLAP_SIZE, MAX_CHUNK_SIZE, BaseParser, ParsedChunk, ParseResult


class DocxParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".docx"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()

        try:
            doc = Document(str(file_path))
        except Exception as e:
            result.errors.append(f"Failed to open DOCX: {e}")
            return result

        result.title = doc.core_properties.title or file_path.stem
        result.author = doc.core_properties.author

        sections: list[tuple[str | None, str]] = []
        current_heading: str | None = None
        current_text: list[str] = []

        for para in doc.paragraphs:
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                if current_text:
                    sections.append((current_heading, "\n".join(current_text)))
                    current_text = []
                current_heading = para.text
            else:
                if para.text.strip():
                    current_text.append(para.text)

        if current_text:
            sections.append((current_heading, "\n".join(current_text)))

        section_num = 0
        for heading, text in sections:
            if not text.strip():
                continue

            section_num += 1

            if len(text) <= MAX_CHUNK_SIZE:
                result.chunks.append(ParsedChunk(
                    content=text,
                    page_number=section_num,
                    section=heading,
                    content_type="text",
                ))
            else:
                start = 0
                while start < len(text):
                    end = min(start + MAX_CHUNK_SIZE, len(text))
                    chunk_text = text[start:end]
                    if chunk_text.strip():
                        result.chunks.append(ParsedChunk(
                            content=chunk_text,
                            page_number=section_num,
                            section=heading,
                            content_type="text",
                        ))
                    if end >= len(text):
                        break
                    start = end - OVERLAP_SIZE

        result.chunks = self.merge_small_chunks(result.chunks)
        result.total_pages = section_num
        return result

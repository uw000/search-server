from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup, Tag
from ebooklib import epub

from app.parsers.base import BaseParser, ParseResult
from app.parsers.text_cleaner import clean_text


_FOOTNOTE_CLASSES = {
    "footnote",
    "footnotes",
    "endnote",
    "endnotes",
    "rearnote",
    "rearnotes",
    "noteref",  # 각주 참조는 본문에서 제거 대상
}
_FOOTNOTE_EPUB_TYPES = ("footnote", "endnote", "rearnote")


def _extract_footnotes(soup: BeautifulSoup) -> list[str]:
    """EPUB DOM 에서 각주/미주 본문을 분리 추출.

    찾은 엘리먼트는 DOM 에서 제거(decompose)하여 본문 텍스트 추출 시 중복되지 않게 한다.
    반환값은 각주 본문 텍스트 리스트.
    """
    notes: list[str] = []

    # 1) EPUB3 표준: epub:type 속성 기반
    for el in list(soup.find_all(attrs={"epub:type": True})):
        if not isinstance(el, Tag):
            continue
        etype = str(el.get("epub:type") or "").lower()
        if any(t in etype for t in _FOOTNOTE_EPUB_TYPES):
            txt = el.get_text(separator="\n", strip=True)
            if txt:
                notes.append(txt)
            el.decompose()

    # 2) 클래스 기반(EPUB2 / Calibre / 일반 관례)
    for tag_name in ("aside", "div", "section"):
        for el in list(soup.find_all(tag_name, class_=True)):
            if not isinstance(el, Tag):
                continue
            classes = {c.lower() for c in (el.get("class") or [])}
            if classes & _FOOTNOTE_CLASSES:
                txt = el.get_text(separator="\n", strip=True)
                if txt:
                    notes.append(txt)
                el.decompose()

    # 3) 본문에 남은 각주 참조(sup/a.noteref 등)는 검색 소음이라 제거
    for ref in list(soup.find_all(attrs={"epub:type": True})):
        if not isinstance(ref, Tag):
            continue
        etype = str(ref.get("epub:type") or "").lower()
        if "noteref" in etype:
            ref.decompose()
    for ref in list(soup.select(".noteref, sup.footnote, sup.footnoteref, a.footnoteref")):
        if isinstance(ref, Tag):
            ref.decompose()

    return notes


class EpubParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".epub"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()

        size_error = self.check_file_size(file_path)
        if size_error:
            result.errors.append(size_error)
            return result

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
            # 문단 경계 보존을 위해 block-level 태그는 줄바꿈 2회로 구분
            for br in soup.find_all("br"):
                br.replace_with("\n")

            # 각주/미주를 먼저 분리 (본문 추출 전)
            footnote_texts = _extract_footnotes(soup)

            text = soup.get_text(separator="\n", strip=True)
            text = clean_text(text, drop_page_numbers=False)

            if not text.strip() and not footnote_texts:
                continue

            chapter_num += 1
            chapter_title = None
            heading = soup.find(["h1", "h2", "h3"])
            if heading:
                chapter_title = heading.get_text(strip=True)

            if text.strip():
                result.chunks.extend(self.chunk_long_text(
                    text,
                    page_number=chapter_num,
                    chapter=chapter_title,
                    content_type="text",
                ))

            if footnote_texts:
                notes_text = clean_text(
                    "\n\n".join(footnote_texts),
                    drop_page_numbers=False,
                )
                if notes_text.strip():
                    result.chunks.extend(self.chunk_long_text(
                        notes_text,
                        page_number=chapter_num,
                        chapter=chapter_title,
                        section=f"Footnotes (Ch.{chapter_num})",
                        content_type="text",
                    ))

        result.chunks = self.merge_small_chunks(result.chunks)
        result.total_pages = chapter_num
        return result

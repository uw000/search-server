"""EPUB 파서 각주 분리 로직 테스트."""
from __future__ import annotations

from bs4 import BeautifulSoup

from app.parsers.epub_parser import _extract_footnotes


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_extract_epub3_aside_footnote() -> None:
    html = """
    <body>
      <p>본문입니다 <sup epub:type="noteref"><a href="#fn1">1</a></sup>.</p>
      <aside epub:type="footnote" id="fn1">
        <p>첫번째 각주 내용.</p>
      </aside>
    </body>
    """
    soup = _soup(html)
    notes = _extract_footnotes(soup)
    assert len(notes) == 1
    assert "첫번째 각주 내용" in notes[0]

    # 본문 추출시 각주/noteref 제거되어야 함
    remaining = soup.get_text(separator="\n", strip=True)
    assert "본문입니다" in remaining
    assert "첫번째 각주 내용" not in remaining
    # noteref 숫자(1) 또한 제거
    assert "첫번째 각주" not in remaining


def test_extract_class_based_footnote_div() -> None:
    html = """
    <body>
      <p>본문.</p>
      <div class="footnote"><p>클래스 기반 각주</p></div>
    </body>
    """
    soup = _soup(html)
    notes = _extract_footnotes(soup)
    assert len(notes) == 1
    assert "클래스 기반 각주" in notes[0]


def test_extract_multiple_types_and_endnotes() -> None:
    html = """
    <body>
      <p>introduction</p>
      <aside class="footnote">first note</aside>
      <aside class="endnote">second note</aside>
      <section class="footnotes">
        <div>third note</div>
      </section>
      <aside epub:type="rearnote">fourth</aside>
    </body>
    """
    soup = _soup(html)
    notes = _extract_footnotes(soup)
    joined = "\n".join(notes)
    assert "first note" in joined
    assert "second note" in joined
    assert "third note" in joined
    assert "fourth" in joined


def test_no_footnotes_returns_empty_and_preserves_body() -> None:
    html = "<body><p>그냥 본문</p><p>more</p></body>"
    soup = _soup(html)
    notes = _extract_footnotes(soup)
    assert notes == []
    text = soup.get_text(separator=" ", strip=True)
    assert "그냥 본문" in text
    assert "more" in text


def test_noteref_sup_removed_from_body() -> None:
    html = """
    <body>
      <p>문장<sup class="footnoteref"><a href="#n1">3</a></sup>.</p>
      <aside class="footnote" id="n1">보조 설명</aside>
    </body>
    """
    soup = _soup(html)
    _ = _extract_footnotes(soup)
    body_text = soup.get_text(separator="", strip=True)
    assert "문장" in body_text
    assert "3" not in body_text  # noteref 숫자 제거 확인

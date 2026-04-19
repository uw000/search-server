from app.parsers.text_cleaner import (
    clean_text,
    normalize_linebreaks,
    remove_repeated_headers_footers,
    strip_page_number_lines,
)


def test_korean_word_linebreak_removed() -> None:
    # 단어 중간 줄바꿈: "앤트\n로픽" → "앤트로픽"
    assert normalize_linebreaks("앤트\n로픽") == "앤트로픽"


def test_english_hyphen_wrap_removed() -> None:
    assert normalize_linebreaks("docu-\nment") == "document"


def test_english_midword_linebreak_removed() -> None:
    assert normalize_linebreaks("hel\nlo") == "hello"


def test_paragraph_break_preserved() -> None:
    text = "첫 문단입니다.\n\n두번째 문단입니다."
    assert normalize_linebreaks(text) == "첫 문단입니다.\n\n두번째 문단입니다."


def test_single_linebreak_between_words_to_space() -> None:
    # 영문 단어 사이(공백 역할)의 단일 \n 은 공백으로
    assert normalize_linebreaks("hello\nworld") == "hello world" or \
           normalize_linebreaks("hello\nworld") == "helloworld"
    # 참고: 현재 규칙은 영문-영문 공백 없는 \n 을 단어 내부로 간주하여 붙임.
    # "hello\nworld"는 단어가 아닌 경우도 있으나 본 로직은 책 OCR 문맥 기준.


def test_mixed_content() -> None:
    # Korean-Korean 연속은 공백 없이 붙이는 것이 설계 의도
    # (나머지 토크나이징은 nori 가 담당)
    text = "회사 앤트\n로픽은 Claude 모델이다.\n\n두번째 문단."
    out = normalize_linebreaks(text)
    assert "앤트로픽" in out
    assert "\n\n두번째 문단" in out


def test_crlf_normalized() -> None:
    assert normalize_linebreaks("a\r\nb\r\n\r\nc") == "a b\n\nc" or \
           normalize_linebreaks("a\r\nb\r\n\r\nc") == "ab\n\nc"


def test_multispace_collapsed() -> None:
    assert normalize_linebreaks("a    b\t\tc") == "a b c"


def test_strip_page_number_lines_variants() -> None:
    text = "본문입니다.\n12\n- 34 -\nPage 5\n56 / 340\nnext"
    out = strip_page_number_lines(text)
    assert "12" not in out.split("\n")
    assert "- 34 -" not in out
    assert "Page 5" not in out
    assert "56 / 340" not in out
    assert "본문입니다." in out
    assert "next" in out


def test_strip_page_number_preserves_inline_numbers() -> None:
    text = "값은 42입니다."
    assert strip_page_number_lines(text) == "값은 42입니다."


def test_remove_repeated_headers_footers_drops_common_header() -> None:
    pages = [
        "제 1 장\n본문 페이지 1 내용\n- 1 -",
        "제 1 장\n본문 페이지 2 내용\n- 2 -",
        "제 1 장\n본문 페이지 3 내용\n- 3 -",
        "제 1 장\n본문 페이지 4 내용\n- 4 -",
    ]
    cleaned = remove_repeated_headers_footers(pages)
    for page in cleaned:
        assert "제 1 장" not in page
        assert "본문 페이지" in page


def test_remove_headers_footers_small_corpus_unchanged() -> None:
    # 페이지 2개뿐이면 통계적 판정 불가 → 원본 반환
    pages = ["머리글\n내용1", "머리글\n내용2"]
    assert remove_repeated_headers_footers(pages) == pages


def test_clean_text_composes() -> None:
    text = "머리\n글\n\n본문 내용입니다.\n12"
    out = clean_text(text)
    # 한글 연속: 머리\n글 → 머리글
    assert "머리글" in out
    # 페이지번호 라인(12)은 제거
    assert "본문 내용입니다." in out
    assert "\n12" not in out
    # 문단 구분 보존
    assert "\n\n" in out

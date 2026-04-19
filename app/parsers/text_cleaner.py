"""OCR 및 전자문서 텍스트 추출 결과의 공통 정제.

파이프라인 위치: 파서의 페이지/섹션 추출 직후, 청크 분할(``split_large_chunk``) 이전.

규칙 (OCR/PDF 출력에 빈번한 패턴):
  1. CRLF/CR → LF 통일
  2. 문단 구분(연속된 빈 줄)을 placeholder 로 잠시 치환하여 보존
  3. 영문 하이픈 줄바꿈 제거: "docu-\\nment" → "document"
  4. 한글-한글 사이 줄바꿈 제거: "앤트\\n로픽" → "앤트로픽"
  5. 영문-영문 사이 줄바꿈(공백 없는) 제거: "hel\\nlo" → "hello"
  6. 그 밖의 단일 \\n 은 공백으로 치환 (문장 내 flow 복원)
  7. 연속 공백 축약
  8. 문단 placeholder 복원 (\\n\\n)

머리글/바닥글 제거는 다중 페이지 맥락이 필요하므로 ``remove_repeated_headers_footers``
에 분리했다. 페이지 번호 단독 라인 제거는 ``strip_page_number_lines``.
"""
from __future__ import annotations

import re
from collections import Counter

__all__ = [
    "normalize_linebreaks",
    "strip_page_number_lines",
    "remove_repeated_headers_footers",
    "clean_text",
]


_PARA_PLACEHOLDER = "\x00PARA\x00"

_RE_MULTI_BLANK = re.compile(r"\n[ \t]*\n[ \t\n]*")
_RE_HYPHEN_WRAP = re.compile(r"([A-Za-z])-\n([A-Za-z])")
_RE_KOR_CONT = re.compile(r"([가-힣])\n([가-힣])")
_RE_EN_CONT = re.compile(r"([A-Za-z])\n([A-Za-z])")
_RE_MULTISPACE = re.compile(r"[ \t]+")

# 페이지번호 단독 라인 패턴: "12", "- 12 -", "12 / 340", "Page 12", "p.12" 등
_RE_PAGE_NUM_LINE = re.compile(
    r"""^\s*(?:
        -\s*\d{1,5}\s*-      # - 12 -
      | p(?:age)?\.?\s*\d{1,5}(?:\s*/\s*\d{1,5})?  # p.12 또는 page 12 또는 12/340
      | \d{1,5}\s*/\s*\d{1,5}  # 12 / 340
      | \d{1,5}                # 숫자만
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def normalize_linebreaks(text: str) -> str:
    """OCR/PDF 추출 텍스트의 줄바꿈을 정규화한다. 문단 구분(\\n\\n)은 보존."""
    if not text:
        return text

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _RE_MULTI_BLANK.sub(_PARA_PLACEHOLDER, text)
    text = _RE_HYPHEN_WRAP.sub(r"\1\2", text)
    text = _RE_KOR_CONT.sub(r"\1\2", text)
    text = _RE_EN_CONT.sub(r"\1\2", text)
    text = text.replace("\n", " ")
    text = _RE_MULTISPACE.sub(" ", text)
    text = text.replace(_PARA_PLACEHOLDER, "\n\n")
    return text.strip()


def strip_page_number_lines(text: str) -> str:
    """페이지 번호만 있는 라인을 제거한다 (문단 내부의 숫자는 건드리지 않음)."""
    if not text:
        return text
    lines = text.split("\n")
    kept = [ln for ln in lines if not _RE_PAGE_NUM_LINE.match(ln)]
    return "\n".join(kept)


def remove_repeated_headers_footers(
    pages: list[str],
    head_lines: int = 2,
    foot_lines: int = 2,
    min_repeat_ratio: float = 0.3,
) -> list[str]:
    """여러 페이지에서 반복되는 머리글/바닥글 라인을 제거.

    각 페이지의 처음 ``head_lines``, 마지막 ``foot_lines`` 범위에서
    전체 페이지의 ``min_repeat_ratio`` 이상 반복 출현한 라인을 찾아 제거한다.
    """
    if len(pages) < 3:
        # 페이지가 너무 적으면 통계적 판별 불가 → 그대로 반환
        return pages

    min_repeat = max(2, int(len(pages) * min_repeat_ratio))
    candidate_counter: Counter[str] = Counter()

    split_pages: list[list[str]] = [p.split("\n") if p else [] for p in pages]

    for lines in split_pages:
        if not lines:
            continue
        head = [ln.strip() for ln in lines[:head_lines] if ln.strip()]
        foot = [ln.strip() for ln in lines[-foot_lines:] if ln.strip()]
        # 같은 페이지 안에서 head/foot 범위가 겹치면 이중 카운트되므로 dedupe
        unique: set[str] = set()
        for ln in head + foot:
            # 너무 긴 라인(본문일 가능성 높음)은 후보 제외
            if 1 <= len(ln) <= 80:
                unique.add(ln)
        for ln in unique:
            candidate_counter[ln] += 1

    repeats = {ln for ln, c in candidate_counter.items() if c >= min_repeat}
    if not repeats:
        return pages

    cleaned: list[str] = []
    for lines in split_pages:
        if not lines:
            cleaned.append("")
            continue

        new_lines = list(lines)
        for i in range(min(head_lines, len(new_lines))):
            if new_lines[i].strip() in repeats:
                new_lines[i] = ""
        for i in range(1, min(foot_lines, len(new_lines)) + 1):
            if new_lines[-i].strip() in repeats:
                new_lines[-i] = ""
        cleaned.append("\n".join(ln for ln in new_lines if ln != ""))

    return cleaned


def clean_text(text: str, drop_page_numbers: bool = True) -> str:
    """파서 공용 편의 함수: 페이지번호 라인 제거 → 줄바꿈 정규화."""
    if not text:
        return text
    if drop_page_numbers:
        text = strip_page_number_lines(text)
    return normalize_linebreaks(text)

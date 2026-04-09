import re

from app.parsers.base import ParseResult

WEIGHT_TEXT_EXTRACTION = 0.4
WEIGHT_AVG_CHAR_COUNT = 0.3
WEIGHT_ABNORMAL_CHARS = 0.2
WEIGHT_STRUCTURE_INFO = 0.1


def calculate_quality_score(result: ParseResult) -> float:
    if not result.chunks:
        return 0.0

    # 1. 텍스트 추출 성공률 (0~1)
    non_empty_chunks = sum(1 for c in result.chunks if c.char_count > 10)
    text_extraction_ratio = non_empty_chunks / len(result.chunks) if result.chunks else 0.0

    # 2. 평균 글자 수 적정성 (0~1)
    avg_chars = sum(c.char_count for c in result.chunks) / len(result.chunks)
    if avg_chars < 50:
        char_score = avg_chars / 50
    elif avg_chars > 3000:
        char_score = max(0.5, 1.0 - (avg_chars - 3000) / 5000)
    else:
        char_score = 1.0

    # 3. 비정상 문자 비율 역수 (0~1)
    total_chars = sum(c.char_count for c in result.chunks)
    if total_chars > 0:
        all_text = "".join(c.content for c in result.chunks)
        abnormal = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]", all_text))
        abnormal_ratio = abnormal / total_chars
        abnormal_score = max(0.0, 1.0 - abnormal_ratio * 10)
    else:
        abnormal_score = 0.0

    # 4. 구조 정보 존재 여부 (0~1)
    has_title = 1.0 if result.title else 0.0
    has_chapters = 1.0 if any(c.chapter for c in result.chunks) else 0.0
    has_sections = 1.0 if any(c.section for c in result.chunks) else 0.0
    structure_score = (has_title + has_chapters + has_sections) / 3

    score = (
        text_extraction_ratio * WEIGHT_TEXT_EXTRACTION
        + char_score * WEIGHT_AVG_CHAR_COUNT
        + abnormal_score * WEIGHT_ABNORMAL_CHARS
        + structure_score * WEIGHT_STRUCTURE_INFO
    )

    return round(min(1.0, max(0.0, score)), 3)


def quality_grade(score: float) -> str:
    if score >= 0.9:
        return "success"
    elif score >= 0.7:
        return "partial"
    else:
        return "failed"

from app.parsers.base import ParsedChunk, ParseResult
from app.parsers.quality_checker import calculate_quality_score, quality_grade


def test_quality_score_good() -> None:
    result = ParseResult(
        chunks=[
            ParsedChunk(content="Good content here. " * 50, chapter="Chapter 1"),
            ParsedChunk(content="More good content. " * 50, chapter="Chapter 2"),
        ],
        title="Test Document",
    )
    score = calculate_quality_score(result)
    assert score >= 0.7


def test_quality_score_empty() -> None:
    result = ParseResult(chunks=[])
    assert calculate_quality_score(result) == 0.0


def test_quality_score_poor() -> None:
    result = ParseResult(
        chunks=[
            ParsedChunk(content="x"),
            ParsedChunk(content="y"),
        ]
    )
    score = calculate_quality_score(result)
    assert score < 0.7


def test_quality_grade() -> None:
    assert quality_grade(0.95) == "success"
    assert quality_grade(0.8) == "partial"
    assert quality_grade(0.5) == "failed"

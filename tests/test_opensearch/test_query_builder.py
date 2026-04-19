"""query_builder 단위 테스트 — OpenSearch 접속 없이 쿼리 바디 구조만 검증."""
from __future__ import annotations

from app.opensearch.query_builder import (
    build_document_search_query,
    build_search_query,
)


def test_build_search_query_basic() -> None:
    body = build_search_query("검색어", page=1, size=20)
    assert body["from"] == 0
    assert body["size"] == 20
    assert "bool" in body["query"]
    should = body["query"]["bool"]["should"]
    assert len(should) == 1
    mm = should[0]["multi_match"]
    assert mm["query"] == "검색어"
    assert mm["operator"] == "or"
    assert mm["minimum_should_match"] == "75%"


def test_build_search_query_fuzziness_default() -> None:
    body = build_search_query("python")
    mm = body["query"]["bool"]["should"][0]["multi_match"]
    assert mm.get("fuzziness") == "AUTO"
    assert mm.get("prefix_length") == 1


def test_build_search_query_fuzziness_disabled() -> None:
    body = build_search_query("python", fuzziness=None)
    mm = body["query"]["bool"]["should"][0]["multi_match"]
    assert "fuzziness" not in mm


def test_build_search_query_has_title_field() -> None:
    body = build_search_query("python")
    mm = body["query"]["bool"]["should"][0]["multi_match"]
    assert any(f.startswith("title") for f in mm["fields"])


def test_build_search_query_has_content_subfields() -> None:
    body = build_search_query("python")
    fields = body["query"]["bool"]["should"][0]["multi_match"]["fields"]
    assert "content^3" in fields
    assert "content.english^2" in fields
    assert "content.ngram^1" in fields


def test_build_search_query_pagination() -> None:
    body = build_search_query("q", page=3, size=20)
    assert body["from"] == 40
    assert body["size"] == 20


def test_build_search_query_format_filter_single() -> None:
    body = build_search_query("q", format_filter="pdf")
    filters = body["query"]["bool"]["filter"]
    assert filters == [{"terms": {"format": ["pdf"]}}]


def test_build_search_query_format_filter_multiple() -> None:
    body = build_search_query("q", format_filter="pdf,epub, docx")
    filters = body["query"]["bool"]["filter"]
    assert filters[0]["terms"]["format"] == ["pdf", "epub", "docx"]


def test_build_search_query_no_filter_when_unset() -> None:
    body = build_search_query("q")
    assert "filter" not in body["query"]["bool"]


def test_build_search_query_highlight_default_on() -> None:
    body = build_search_query("q")
    assert "highlight" in body
    hl = body["highlight"]["fields"]["content"]
    assert hl["pre_tags"] == ["<mark>"]
    assert hl["post_tags"] == ["</mark>"]


def test_build_search_query_highlight_off() -> None:
    body = build_search_query("q", highlight=False)
    assert "highlight" not in body


def test_build_search_query_collapse() -> None:
    body = build_search_query("q")
    assert body["collapse"]["field"] == "doc_id"
    assert body["collapse"]["inner_hits"]["size"] == 3


def test_build_search_query_sort_score() -> None:
    body = build_search_query("q", sort="_score")
    assert body["sort"] == [{"_score": "desc"}]


def test_build_search_query_sort_date() -> None:
    body = build_search_query("q", sort="date")
    assert body["sort"][0] == {"indexed_at": "desc"}


def test_build_search_query_sort_title_uses_title_keyword() -> None:
    """예전 버그(chapter.keyword 로 정렬)가 재발하지 않도록 회귀 보호."""
    body = build_search_query("q", sort="title")
    first_sort_key = next(iter(body["sort"][0]))
    assert first_sort_key == "title"
    assert "chapter" not in str(body["sort"])


def test_build_document_search_query_basic() -> None:
    body = build_document_search_query("Claude", page=1, size=10)
    assert body["from"] == 0
    assert body["size"] == 10
    mm = body["query"]["multi_match"]
    assert mm["query"] == "Claude"
    assert "title^3" in mm["fields"]
    assert mm.get("fuzziness") == "AUTO"


def test_build_document_search_query_pagination() -> None:
    body = build_document_search_query("q", page=5, size=10)
    assert body["from"] == 40

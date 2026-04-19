from typing import Any


def build_search_query(
    query: str,
    page: int = 1,
    size: int = 20,
    format_filter: str | None = None,
    sort: str = "_score",
    highlight: bool = True,
    fuzziness: str | None = "AUTO",
) -> dict[str, Any]:
    """chunks 인덱스용 검색 쿼리.

    필드 가중치:
      title^4           — chunks 에 복사 저장된 문서 제목 (keyword — 완전 일치 시 강한 가중)
      content^3         — 본문 (nori 형태소 분석)
      chapter^2         — 챕터 제목 (nori)
      content.english^2 — 영문 스테밍
      content.standard^2— 원형 보존 (코드/변수명 정확 매칭)
      content.ngram^1   — 부분 문자열/자소 보완
    """
    from_offset = (page - 1) * size

    multi_match_clause: dict[str, Any] = {
        "query": query,
        "fields": [
            "title^4",
            "content^3",
            "chapter^2",
            "content.english^2",
            "content.standard^2",
            "content.ngram^1",
        ],
        "type": "best_fields",
        "operator": "or",
        "minimum_should_match": "75%",
    }
    if fuzziness:
        multi_match_clause["fuzziness"] = fuzziness
        multi_match_clause["prefix_length"] = 1

    should_clauses: list[dict] = [{"multi_match": multi_match_clause}]

    filter_clauses: list[dict] = []
    if format_filter:
        formats = [f.strip() for f in format_filter.split(",")]
        filter_clauses.append({"terms": {"format": formats}})

    bool_query: dict[str, Any] = {"should": should_clauses, "minimum_should_match": 1}
    if filter_clauses:
        bool_query["filter"] = filter_clauses

    body: dict[str, Any] = {
        "query": {"bool": bool_query},
        "from": from_offset,
        "size": size,
        "collapse": {
            "field": "doc_id",
            "inner_hits": {
                "name": "pages",
                "size": 3,
                "sort": [{"_score": "desc"}],
            },
        },
    }

    if highlight:
        body["highlight"] = {
            "fields": {
                "content": {
                    "fragment_size": 200,
                    "number_of_fragments": 3,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                }
            }
        }

    if sort == "_score":
        body["sort"] = [{"_score": "desc"}]
    elif sort == "date":
        body["sort"] = [{"indexed_at": "desc"}, {"_score": "desc"}]
    elif sort == "title":
        body["sort"] = [{"title": "asc"}, {"_score": "desc"}]

    return body


def build_document_search_query(
    query: str,
    page: int = 1,
    size: int = 20,
    fuzziness: str | None = "AUTO",
) -> dict[str, Any]:
    from_offset = (page - 1) * size

    multi_match_clause: dict[str, Any] = {
        "query": query,
        "fields": ["title^3", "title.english^2", "author^1", "tags^1"],
        "type": "best_fields",
    }
    if fuzziness:
        multi_match_clause["fuzziness"] = fuzziness
        multi_match_clause["prefix_length"] = 1

    return {
        "query": {"multi_match": multi_match_clause},
        "from": from_offset,
        "size": size,
    }

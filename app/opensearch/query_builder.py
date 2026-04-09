from typing import Any


def build_search_query(
    query: str,
    page: int = 1,
    size: int = 20,
    format_filter: str | None = None,
    sort: str = "_score",
    highlight: bool = True,
) -> dict[str, Any]:
    from_offset = (page - 1) * size

    must_clauses: list[dict] = []
    should_clauses: list[dict] = [
        {
            "multi_match": {
                "query": query,
                "fields": [
                    "content^3",
                    "content.english^2",
                    "content.standard^2",
                    "content.ngram^1",
                    "chapter^1.5",
                ],
                "type": "best_fields",
                "operator": "or",
                "minimum_should_match": "75%",
            }
        }
    ]

    filter_clauses: list[dict] = []
    if format_filter:
        formats = [f.strip() for f in format_filter.split(",")]
        filter_clauses.append({"terms": {"doc_id": formats}})

    bool_query: dict[str, Any] = {"should": should_clauses, "minimum_should_match": 1}
    if must_clauses:
        bool_query["must"] = must_clauses
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
        body["sort"] = [{"chapter.keyword": "asc"}, {"_score": "desc"}]

    return body


def build_document_search_query(
    query: str,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    from_offset = (page - 1) * size

    return {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^3", "title.english^2", "author^1", "tags^1"],
                "type": "best_fields",
            }
        },
        "from": from_offset,
        "size": size,
    }

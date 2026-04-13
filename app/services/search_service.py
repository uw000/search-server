import logging
import uuid
from typing import Any

from opensearchpy import OpenSearchException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_history import SearchHistory
from app.opensearch.client import get_opensearch_client
from app.opensearch.index_manager import CHUNKS_INDEX, DOCUMENTS_INDEX
from app.opensearch.query_builder import build_document_search_query, build_search_query

logger = logging.getLogger(__name__)


async def search_chunks(
    query: str,
    page: int = 1,
    size: int = 20,
    format_filter: str | None = None,
    sort: str = "_score",
    highlight: bool = True,
) -> dict[str, Any]:
    client = get_opensearch_client()
    body = build_search_query(
        query=query,
        page=page,
        size=size,
        format_filter=format_filter,
        sort=sort,
        highlight=highlight,
    )

    try:
        response = await client.search(index=CHUNKS_INDEX, body=body)
    except OpenSearchException as e:
        logger.error(f"Search failed for query '{query}': {e}")
        return {
            "query": query, "total": 0, "page": page, "size": size,
            "took_ms": 0, "results": [], "error": str(e),
        }

    hits = response["hits"]
    total = hits["total"]["value"]
    took_ms = response["took"]

    # 검색된 doc_id들의 메타데이터를 documents 인덱스에서 일괄 조회
    doc_ids = {hit["_source"].get("doc_id") for hit in hits["hits"] if hit["_source"].get("doc_id")}
    doc_meta = await _fetch_document_metadata(client, doc_ids) if doc_ids else {}

    results = []
    for hit in hits["hits"]:
        source = hit["_source"]
        doc_id = source.get("doc_id")
        meta = doc_meta.get(doc_id, {})

        result_item: dict[str, Any] = {
            "doc_id": doc_id,
            "chunk_id": source.get("chunk_id"),
            "title": source.get("title") or meta.get("title"),
            "author": meta.get("author"),
            "format": source.get("format") or meta.get("format"),
            "file_name": source.get("file_name") or meta.get("file_name"),
            "page_number": source.get("page_number"),
            "chapter": source.get("chapter"),
            "content_type": source.get("content_type"),
            "is_ocr": source.get("is_ocr", False),
            "score": hit["_score"],
        }

        if highlight and "highlight" in hit:
            result_item["highlight"] = hit["highlight"].get("content", [])
        else:
            content = source.get("content", "")
            result_item["highlight"] = [content[:200] + "..." if len(content) > 200 else content]

        # inner_hits (collapsed pages)
        inner = hit.get("inner_hits", {}).get("pages", {}).get("hits", {}).get("hits", [])
        result_item["inner_pages"] = [
            {
                "page_number": ih["_source"].get("page_number"),
                "score": ih["_score"],
                "highlight": ih.get("highlight", {}).get("content", []),
            }
            for ih in inner
        ]

        results.append(result_item)

    return {
        "query": query,
        "total": total,
        "page": page,
        "size": size,
        "took_ms": took_ms,
        "results": results,
    }


async def _fetch_document_metadata(client, doc_ids: set[str]) -> dict[str, dict]:
    """documents 인덱스에서 여러 문서의 메타데이터를 일괄 조회."""
    try:
        resp = await client.mget(
            index=DOCUMENTS_INDEX,
            body={"ids": list(doc_ids)},
        )
        result = {}
        for doc in resp.get("docs", []):
            if doc.get("found"):
                source = doc["_source"]
                result[source.get("doc_id", doc["_id"])] = {
                    "title": source.get("title"),
                    "author": source.get("author"),
                    "format": source.get("format"),
                    "file_name": source.get("file_name"),
                }
        return result
    except OpenSearchException:
        logger.warning("Failed to fetch document metadata from OpenSearch")
        return {}


async def search_documents(
    query: str,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    client = get_opensearch_client()
    body = build_document_search_query(query=query, page=page, size=size)

    try:
        response = await client.search(index=DOCUMENTS_INDEX, body=body)
    except OpenSearchException as e:
        logger.error(f"Document search failed for query '{query}': {e}")
        return {
            "query": query, "total": 0, "page": page, "size": size,
            "took_ms": 0, "results": [], "error": str(e),
        }

    hits = response["hits"]
    results = []
    for hit in hits["hits"]:
        source = hit["_source"]
        results.append({
            "doc_id": source.get("doc_id"),
            "title": source.get("title"),
            "author": source.get("author"),
            "format": source.get("format"),
            "total_pages": source.get("total_pages"),
            "tags": source.get("tags", []),
            "score": hit["_score"],
        })

    return {
        "query": query,
        "total": hits["total"]["value"],
        "page": page,
        "size": size,
        "took_ms": response["took"],
        "results": results,
    }


async def save_search_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    result_count: int,
    took_ms: int,
    filters: dict | None = None,
) -> None:
    history = SearchHistory(
        user_id=user_id,
        query=query,
        result_count=result_count,
        took_ms=took_ms,
        filters=filters,
    )
    db.add(history)
    await db.flush()

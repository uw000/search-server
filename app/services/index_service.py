import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from opensearchpy import OpenSearchException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.file import File
from app.models.tag import Tag
from app.opensearch.client import get_opensearch_client
from app.opensearch.index_manager import CHUNKS_INDEX, DOCUMENTS_INDEX

logger = logging.getLogger(__name__)


async def index_document(db: AsyncSession, file_id: uuid.UUID) -> dict[str, Any]:
    client = get_opensearch_client()

    result = await db.execute(select(File).where(File.file_id == file_id))
    file = result.scalar_one_or_none()
    if file is None:
        raise ValueError(f"File not found: {file_id}")

    # tags
    tag_result = await db.execute(select(Tag.tag).where(Tag.file_id == file_id))
    tags = [row[0] for row in tag_result.all()]

    # documents 인덱스에 메타데이터 인덱싱
    doc_body = {
        "doc_id": str(file.file_id),
        "title": file.title,
        "author": file.author,
        "format": file.format,
        "file_name": file.file_name,
        "total_pages": file.total_pages,
        "total_chunks": file.total_chunks,
        "parse_quality": file.parse_quality,
        "has_ocr_pages": file.has_ocr_pages,
        "tags": tags,
        "language": file.language,
        "indexed_at": datetime.now(UTC).isoformat(),
    }

    try:
        await client.index(index=DOCUMENTS_INDEX, id=str(file.file_id), body=doc_body)
    except OpenSearchException as e:
        logger.error(f"Failed to index document metadata {file_id}: {e}")
        raise

    # chunks 인덱스에 벌크 인덱싱
    chunk_result = await db.execute(
        select(Chunk)
        .where(Chunk.file_id == file_id)
        .order_by(Chunk.page_number.asc().nulls_last())
    )
    chunks = chunk_result.scalars().all()

    if chunks:
        # 벌크 요청 구성
        bulk_body: list[dict] = []
        for chunk in chunks:
            bulk_body.append({"index": {"_index": CHUNKS_INDEX, "_id": str(chunk.chunk_id)}})
            bulk_body.append({
                "chunk_id": str(chunk.chunk_id),
                "doc_id": str(file.file_id),
                "format": file.format,
                "file_name": file.file_name,
                "title": file.title,
                "page_number": chunk.page_number,
                "chapter": chunk.chapter,
                "section": chunk.section,
                "content": chunk.content,
                "content_type": chunk.content_type,
                "is_ocr": chunk.is_ocr,
                "char_count": chunk.char_count,
            })

        try:
            resp = await client.bulk(body=bulk_body)
            if resp.get("errors"):
                failed = [
                    item for item in resp["items"]
                    if "error" in item.get("index", {})
                ]
                logger.warning(f"Bulk index partial failure for {file_id}: {len(failed)} errors")
        except OpenSearchException as e:
            logger.error(f"Bulk index failed for {file_id}: {e}")
            raise

    # 인덱싱 시간 갱신
    file.indexed_at = datetime.now(UTC)
    file.index_version += 1
    await db.flush()

    return {
        "file_id": str(file_id),
        "document_indexed": True,
        "chunks_indexed": len(chunks),
    }


async def delete_document_index(file_id: uuid.UUID, db: AsyncSession | None = None) -> dict[str, Any]:
    client = get_opensearch_client()

    try:
        await client.delete(index=DOCUMENTS_INDEX, id=str(file_id))
    except OpenSearchException:
        logger.debug(f"Document {file_id} not found in documents index (already deleted)")

    try:
        delete_body = {"query": {"term": {"doc_id": str(file_id)}}}
        result = await client.delete_by_query(index=CHUNKS_INDEX, body=delete_body)
        return {
            "file_id": str(file_id),
            "chunks_deleted": result.get("deleted", 0),
        }
    except OpenSearchException as e:
        logger.error(f"Failed to delete chunks for {file_id}: {e}")
        return {"file_id": str(file_id), "chunks_deleted": 0, "error": str(e)}


async def reindex_all(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(File).where(File.parse_status.in_(["success", "partial"]))
    )
    files = result.scalars().all()

    indexed = 0
    errors = []
    for file in files:
        try:
            await index_document(db, file.file_id)
            indexed += 1
        except Exception as e:
            errors.append({"file_id": str(file.file_id), "error": str(e)})

    return {"indexed": indexed, "errors": errors, "total": len(files)}

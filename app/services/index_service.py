import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.file import File
from app.models.tag import Tag
from app.opensearch.client import get_opensearch_client
from app.opensearch.index_manager import CHUNKS_INDEX, DOCUMENTS_INDEX


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

    await client.index(index=DOCUMENTS_INDEX, id=str(file.file_id), body=doc_body)

    # chunks 인덱스에 텍스트 인덱싱
    chunk_result = await db.execute(
        select(Chunk).where(Chunk.file_id == file_id).order_by(Chunk.page_number)
    )
    chunks = chunk_result.scalars().all()

    indexed_chunks = 0
    for chunk in chunks:
        chunk_body = {
            "chunk_id": str(chunk.chunk_id),
            "doc_id": str(file.file_id),
            "page_number": chunk.page_number,
            "chapter": chunk.chapter,
            "section": chunk.section,
            "content": chunk.content,
            "content_type": chunk.content_type,
            "is_ocr": chunk.is_ocr,
            "char_count": chunk.char_count,
        }
        await client.index(index=CHUNKS_INDEX, id=str(chunk.chunk_id), body=chunk_body)
        indexed_chunks += 1

    # 인덱싱 시간 갱신
    file.indexed_at = datetime.now(UTC)
    file.index_version += 1
    await db.flush()

    return {
        "file_id": str(file_id),
        "document_indexed": True,
        "chunks_indexed": indexed_chunks,
    }


async def delete_document_index(file_id: uuid.UUID, db: AsyncSession | None = None) -> dict[str, Any]:
    client = get_opensearch_client()

    # documents 인덱스에서 삭제
    try:
        await client.delete(index=DOCUMENTS_INDEX, id=str(file_id))
    except Exception:
        pass

    # chunks 인덱스에서 해당 문서의 모든 청크 삭제
    delete_body = {"query": {"term": {"doc_id": str(file_id)}}}
    result = await client.delete_by_query(index=CHUNKS_INDEX, body=delete_body)

    return {
        "file_id": str(file_id),
        "chunks_deleted": result.get("deleted", 0),
    }


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

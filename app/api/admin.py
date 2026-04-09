from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_db
from app.models.chunk import Chunk
from app.models.file import File
from app.models.user import User
from app.services.document_service import scan_document_folder
from app.services.index_service import reindex_all

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
async def system_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    # 문서 수
    doc_count = await db.execute(select(func.count()).select_from(File))
    total_documents = doc_count.scalar() or 0

    # 청크 수
    chunk_count = await db.execute(select(func.count()).select_from(Chunk))
    total_chunks = chunk_count.scalar() or 0

    # 사용자 수
    user_count = await db.execute(select(func.count()).select_from(User))
    total_users = user_count.scalar() or 0

    # 파싱 상태별 카운트
    status_result = await db.execute(
        select(File.parse_status, func.count()).group_by(File.parse_status)
    )
    parse_status_counts = {row[0]: row[1] for row in status_result.all()}

    # 포맷별 카운트
    format_result = await db.execute(
        select(File.format, func.count()).group_by(File.format)
    )
    formats_counts = {row[0]: row[1] for row in format_result.all()}

    return {
        "total_documents": total_documents,
        "total_chunks": total_chunks,
        "total_users": total_users,
        "parse_status_counts": parse_status_counts,
        "formats_counts": formats_counts,
    }


@router.get("/parse-status")
async def parse_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> list[dict]:
    result = await db.execute(
        select(File).order_by(File.updated_at.desc()).limit(100)
    )
    files = result.scalars().all()

    return [
        {
            "file_id": str(f.file_id),
            "file_name": f.file_name,
            "format": f.format,
            "parse_status": f.parse_status,
            "parse_quality": f.parse_quality,
            "parse_error": f.parse_error,
        }
        for f in files
    ]


@router.post("/reindex-all")
async def reindex_all_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    result = await reindex_all(db)
    return {"message": "Reindex complete", **result}


@router.post("/scan-folder")
async def scan_folder(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    result = await scan_document_folder(db)
    return {"message": "Scan complete", **result}

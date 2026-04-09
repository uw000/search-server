import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.document_service import (
    delete_document as svc_delete_document,
    get_document as svc_get_document,
    list_documents as svc_list_documents,
    register_file,
    save_upload,
)
from app.services.index_service import delete_document_index, index_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    format: Annotated[str | None, Query()] = None,
    parse_status: Annotated[str | None, Query()] = None,
) -> dict:
    return await svc_list_documents(
        db, page=page, size=size, format_filter=format, status_filter=parse_status
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DocumentResponse:
    doc = await svc_get_document(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    # OpenSearch에서 먼저 삭제
    await delete_document_index(doc_id)
    # DB에서 삭제
    deleted = await svc_delete_document(db, doc_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"message": "Document deleted", "doc_id": str(doc_id)}


@router.post("/upload")
async def upload_document(
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin", "editor"))],
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename required")

    supported_exts = {".pdf", ".epub", ".docx", ".txt", ".hwp"}
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in supported_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {ext}. Supported: {supported_exts}",
        )

    content = await file.read()
    dest_path = await save_upload(content, file.filename)
    db_file = await register_file(db, dest_path)

    # Celery 파싱 태스크 큐 등록
    try:
        from workers.tasks.parse_task import parse_file
        parse_file.delay(str(db_file.file_id))
        queued = True
    except Exception:
        queued = False

    return {
        "message": "File uploaded successfully.",
        "file_id": str(db_file.file_id),
        "file_name": db_file.file_name,
        "parse_status": db_file.parse_status,
        "parse_queued": queued,
    }


@router.post("/reindex/{doc_id}")
async def reindex_document(
    doc_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    doc = await svc_get_document(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    result = await index_document(db, doc_id)
    return {"message": "Reindexing complete", **result}

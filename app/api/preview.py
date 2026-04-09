import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.preview_service import get_download_path, get_image_preview, get_text_preview

router = APIRouter(prefix="/api/preview", tags=["preview"])


@router.get("/{doc_id}/text/{page_num}")
async def preview_text(
    doc_id: uuid.UUID,
    page_num: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    result = await get_text_preview(db, doc_id, page_num)
    if not result["pages"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return result


@router.get("/{doc_id}/image/{page_num}")
async def preview_image(
    doc_id: uuid.UUID,
    page_num: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    dpi: Annotated[int, Query(ge=72, le=300)] = 150,
    current_user: User = Depends(get_current_user),
) -> Response:
    image_bytes = await get_image_preview(db, doc_id, page_num, dpi=dpi)
    if image_bytes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found or not a PDF")
    return Response(content=image_bytes, media_type="image/jpeg")


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    result = await get_download_path(db, doc_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path, file_name = result
    return FileResponse(path=str(file_path), filename=file_name)

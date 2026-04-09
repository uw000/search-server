import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/preview", tags=["preview"])


@router.get("/{doc_id}/text/{page_num}")
async def preview_text(
    doc_id: uuid.UUID,
    page_num: int,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    raise NotImplementedError("Text preview not yet implemented")


@router.get("/{doc_id}/image/{page_num}")
async def preview_image(
    doc_id: uuid.UUID,
    page_num: int,
    dpi: Annotated[int, Query(ge=72, le=300)] = 150,
    current_user: User = Depends(get_current_user),
) -> dict:
    raise NotImplementedError("Image preview not yet implemented")


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    raise NotImplementedError("Download not yet implemented")

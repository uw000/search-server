import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile

from app.api.deps import get_current_user, require_role
from app.models.user import User

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
async def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    raise NotImplementedError("List documents not yet implemented")


@router.get("/{doc_id}")
async def get_document(
    doc_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    raise NotImplementedError("Get document not yet implemented")


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise NotImplementedError("Delete document not yet implemented")


@router.post("/upload")
async def upload_document(
    file: UploadFile,
    current_user: Annotated[User, Depends(require_role("admin", "editor"))],
) -> dict:
    raise NotImplementedError("Upload document not yet implemented")


@router.post("/reindex/{doc_id}")
async def reindex_document(
    doc_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise NotImplementedError("Reindex document not yet implemented")

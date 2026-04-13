import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_db
from app.models.file import File
from app.models.tag import Tag
from app.models.user import User

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagCreate(BaseModel):
    tag: str


class TagListResponse(BaseModel):
    file_id: str
    tags: list[str]


@router.get("/{doc_id}", response_model=TagListResponse)
async def get_tags(
    doc_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TagListResponse:
    result = await db.execute(select(Tag.tag).where(Tag.file_id == doc_id).order_by(Tag.tag))
    tags = [row[0] for row in result.all()]
    return TagListResponse(file_id=str(doc_id), tags=tags)


@router.post("/{doc_id}", status_code=status.HTTP_201_CREATED)
async def add_tag(
    doc_id: uuid.UUID,
    data: TagCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin", "editor"))],
) -> dict:
    # 문서 존재 확인
    file_result = await db.execute(select(File).where(File.file_id == doc_id))
    if file_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # 중복 확인
    existing = await db.execute(
        select(Tag).where(Tag.file_id == doc_id, Tag.tag == data.tag)
    )
    if existing.scalar_one_or_none():
        return {"message": "Tag already exists", "tag": data.tag}

    tag = Tag(file_id=doc_id, tag=data.tag)
    db.add(tag)
    await db.flush()
    return {"message": "Tag added", "tag": data.tag}


@router.delete("/{doc_id}/{tag}")
async def remove_tag(
    doc_id: uuid.UUID,
    tag: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin", "editor"))],
) -> dict:
    result = await db.execute(
        select(Tag).where(Tag.file_id == doc_id, Tag.tag == tag)
    )
    tag_obj = result.scalar_one_or_none()
    if tag_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    await db.delete(tag_obj)
    await db.flush()
    return {"message": "Tag removed", "tag": tag}

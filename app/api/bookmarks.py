import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.bookmark import Bookmark
from app.models.file import File
from app.models.user import User
from app.schemas.bookmark import BookmarkCreate, BookmarkResponse, BookmarkUpdate

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


@router.get("", response_model=list[BookmarkResponse])
async def list_bookmarks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[BookmarkResponse]:
    result = await db.execute(
        select(Bookmark, File.file_name, File.title)
        .join(File, Bookmark.file_id == File.file_id)
        .where(Bookmark.user_id == current_user.user_id)
        .order_by(Bookmark.created_at.desc())
    )
    rows = result.all()

    return [
        BookmarkResponse(
            user_id=bm.user_id,
            file_id=bm.file_id,
            note=bm.note,
            created_at=bm.created_at,
            file_name=file_name,
            title=title,
        )
        for bm, file_name, title in rows
    ]


@router.post("", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
async def create_bookmark(
    data: BookmarkCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BookmarkResponse:
    # 문서 존재 확인
    file_result = await db.execute(select(File).where(File.file_id == data.file_id))
    file = file_result.scalar_one_or_none()
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # 중복 확인
    existing = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == current_user.user_id,
            Bookmark.file_id == data.file_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already bookmarked")

    bookmark = Bookmark(
        user_id=current_user.user_id,
        file_id=data.file_id,
        note=data.note,
    )
    db.add(bookmark)
    await db.flush()

    return BookmarkResponse(
        user_id=bookmark.user_id,
        file_id=bookmark.file_id,
        note=bookmark.note,
        created_at=bookmark.created_at,
        file_name=file.file_name,
        title=file.title,
    )


@router.put("/{file_id}", response_model=BookmarkResponse)
async def update_bookmark(
    file_id: uuid.UUID,
    data: BookmarkUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BookmarkResponse:
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == current_user.user_id,
            Bookmark.file_id == file_id,
        )
    )
    bookmark = result.scalar_one_or_none()
    if bookmark is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")

    bookmark.note = data.note
    await db.flush()

    file_result = await db.execute(select(File).where(File.file_id == file_id))
    file = file_result.scalar_one_or_none()

    return BookmarkResponse(
        user_id=bookmark.user_id,
        file_id=bookmark.file_id,
        note=bookmark.note,
        created_at=bookmark.created_at,
        file_name=file.file_name if file else None,
        title=file.title if file else None,
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(
    file_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == current_user.user_id,
            Bookmark.file_id == file_id,
        )
    )
    bookmark = result.scalar_one_or_none()
    if bookmark is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")

    await db.delete(bookmark)
    await db.flush()

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.search_history import SearchHistory
from app.models.user import User

router = APIRouter(prefix="/api/history", tags=["history"])


class SearchHistoryResponse(BaseModel):
    search_id: uuid.UUID
    query: str
    result_count: int | None
    took_ms: int | None
    searched_at: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[SearchHistoryResponse])
async def get_search_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SearchHistoryResponse]:
    result = await db.execute(
        select(SearchHistory)
        .where(SearchHistory.user_id == current_user.user_id)
        .order_by(SearchHistory.searched_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()

    return [
        SearchHistoryResponse(
            search_id=h.search_id,
            query=h.query,
            result_count=h.result_count,
            took_ms=h.took_ms,
            searched_at=h.searched_at.isoformat() if h.searched_at else "",
        )
        for h in rows
    ]


@router.delete("")
async def clear_search_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    result = await db.execute(
        select(SearchHistory).where(SearchHistory.user_id == current_user.user_id)
    )
    rows = result.scalars().all()
    for row in rows:
        await db.delete(row)
    await db.flush()
    return {"message": "Search history cleared", "deleted": len(rows)}

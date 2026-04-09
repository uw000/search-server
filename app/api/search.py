from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.search_service import save_search_history, search_chunks

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search(
    q: Annotated[str, Query(description="검색어")],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    format: Annotated[str | None, Query(description="포맷 필터 (pdf,epub,docx,txt)")] = None,
    sort: Annotated[str, Query(description="정렬 (_score, date, title)")] = "_score",
    highlight: Annotated[bool, Query()] = True,
) -> dict:
    result = await search_chunks(
        query=q,
        page=page,
        size=size,
        format_filter=format,
        sort=sort,
        highlight=highlight,
    )

    await save_search_history(
        db=db,
        user_id=current_user.user_id,
        query=q,
        result_count=result["total"],
        took_ms=result["took_ms"],
        filters={"format": format, "sort": sort} if format else None,
    )

    return result

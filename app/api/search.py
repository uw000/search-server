from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search(
    q: Annotated[str, Query(description="검색어")],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    format: Annotated[str | None, Query(description="포맷 필터")] = None,
    sort: Annotated[str, Query()] = "_score",
    highlight: Annotated[bool, Query()] = True,
    current_user: User = Depends(get_current_user),
) -> dict:
    raise NotImplementedError("Search endpoint not yet implemented")

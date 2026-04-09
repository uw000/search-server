from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.models.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
async def system_stats(
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise NotImplementedError("System stats not yet implemented")


@router.get("/parse-status")
async def parse_status(
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise NotImplementedError("Parse status not yet implemented")


@router.post("/reindex-all")
async def reindex_all(
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise NotImplementedError("Reindex all not yet implemented")


@router.post("/scan-folder")
async def scan_folder(
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise NotImplementedError("Scan folder not yet implemented")

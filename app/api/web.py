"""웹 페이지 라우터 (HTML 렌더링).

쿠키 기반 인증으로 JWT 토큰을 확인합니다.
"""

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.services.user_service import get_user_by_id, list_users

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["web"])


async def _get_user_from_cookie(request: Request, db: AsyncSession):
    """쿠키에서 JWT 토큰을 추출하여 사용자 반환. 실패 시 None."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = uuid.UUID(payload["sub"])
        return await get_user_by_id(db, user_id)
    except (JWTError, KeyError, ValueError):
        return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await authenticate_user(db, username, password)
    if user is None:
        return templates.TemplateResponse(
            request, "login.html", {"error": "사용자명 또는 비밀번호가 올바르지 않습니다."}
        )

    access_token = create_access_token(user.user_id, user.role)
    refresh_token = create_refresh_token(user.user_id)

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return response


@router.get("/logout")
async def web_logout() -> Response:
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def index_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(request, "search.html", {"user": user})


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    page: int = 1,
    size: int = 20,
    format: str | None = None,
    sort: str = "_score",
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    context: dict = {
        "user": user,
        "query": q,
        "page": page,
        "size": size,
        "format_filter": format,
        "sort": sort,
    }

    if q:
        from app.services.search_service import save_search_history, search_chunks

        try:
            result = await search_chunks(
                query=q, page=page, size=size, format_filter=format, sort=sort
            )
            context.update(result)

            await save_search_history(
                db=db, user_id=user.user_id, query=q,
                result_count=result["total"], took_ms=result["took_ms"],
            )
        except Exception:
            context["results"] = []
            context["total"] = 0
            context["took_ms"] = 0

    # HTMX 요청이면 partial만 반환
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "results.html", context)

    return templates.TemplateResponse(request, "search.html", context)


@router.get("/document/{doc_id}", response_class=HTMLResponse)
async def document_detail_page(
    request: Request,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    from app.services.document_service import get_document

    document = await get_document(db, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return templates.TemplateResponse(
        request, "document_detail.html", {"user": user, "document": document}
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user_from_cookie(request, db)
    if user is None or user.role != "admin":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    from sqlalchemy import func, select

    from app.models.chunk import Chunk
    from app.models.file import File
    from app.models.user import User

    doc_count = (await db.execute(select(func.count()).select_from(File))).scalar() or 0
    chunk_count = (await db.execute(select(func.count()).select_from(Chunk))).scalar() or 0
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0

    status_result = await db.execute(
        select(File.parse_status, func.count()).group_by(File.parse_status)
    )
    parse_status_counts = dict(status_result.all())

    format_result = await db.execute(
        select(File.format, func.count()).group_by(File.format)
    )
    formats_counts = dict(format_result.all())

    stats = {
        "total_documents": doc_count,
        "total_chunks": chunk_count,
        "total_users": user_count,
        "parse_status_counts": parse_status_counts,
        "formats_counts": formats_counts,
    }

    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"user": user, "stats": stats}
    )


@router.post("/admin/scan")
async def admin_scan(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user_from_cookie(request, db)
    if user is None or user.role != "admin":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    from app.services.document_service import scan_document_folder

    await scan_document_folder(db)
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)


@router.post("/admin/reindex")
async def admin_reindex(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user_from_cookie(request, db)
    if user is None or user.role != "admin":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    from app.services.index_service import reindex_all

    await reindex_all(db)
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user_from_cookie(request, db)
    if user is None or user.role != "admin":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    users = await list_users(db)
    return templates.TemplateResponse(
        request, "admin/users.html", {"user": user, "users": users}
    )

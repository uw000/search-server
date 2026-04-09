from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.preview import router as preview_router
from app.api.search import router as search_router
from app.api.users import router as users_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(search_router)
api_router.include_router(documents_router)
api_router.include_router(preview_router)
api_router.include_router(admin_router)

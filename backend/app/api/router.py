from fastapi import APIRouter

from backend.app.api.routes.admin import router as admin_router
from backend.app.api.routes.admin_auth import router as admin_auth_router
from backend.app.api.routes.announcements import router as announcement_router
from backend.app.api.routes.chat import router as chat_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.glossary import (
    admin_router as glossary_admin_router,
    public_router as glossary_public_router,
)


api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(announcement_router)
api_router.include_router(glossary_public_router)
api_router.include_router(chat_router)
api_router.include_router(admin_auth_router)
api_router.include_router(admin_router)
api_router.include_router(glossary_admin_router)

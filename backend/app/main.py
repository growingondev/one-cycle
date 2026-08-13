from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.core.config import settings


def create_app() -> FastAPI:
    """FastAPI 애플리케이션을 생성한다."""
    application = FastAPI(
        title=settings.app_name,
        description="LH 공고문 기반 AI 질의응답 서비스 API",
        version=settings.app_version,
        debug=settings.debug,
    )

    application.include_router(api_router)

    return application


app = create_app()
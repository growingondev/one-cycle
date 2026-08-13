from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.config import settings
from backend.app.db.session import engine


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
async def health_check() -> dict[str, str]:
    """백엔드 서버의 실행 상태를 확인한다."""
    return {
        "status": "ok",
        "environment": settings.app_environment,
        "version": settings.app_version,
    }


@router.get("/db")
def database_health_check() -> dict[str, str]:
    """PostgreSQL 연결 상태를 확인한다."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
    }
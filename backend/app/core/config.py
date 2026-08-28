from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """애플리케이션 공통 환경설정."""

    app_name: str = "One Cycle API"
    app_version: str = "0.1.0"
    app_environment: str = "local"
    debug: bool = True

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "one_cycle"
    postgres_user: str = "one_cycle"
    postgres_password: str = "change_me"

    embedding_model_name: str = "BAAI/bge-m3"

    # Internal Docker HTTP Services
    rag_service_base_url: str = ""
    rag_service_timeout_seconds: float = 60.0

    document_worker_base_url: str = ""
    document_worker_timeout_seconds: float = 600.0

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """환경설정을 한 번만 생성하여 재사용한다."""
    return Settings()


settings = get_settings()

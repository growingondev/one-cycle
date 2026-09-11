from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    document_processing_max_attempts: int = 3
    document_processing_retry_delay_seconds: float = 5.0

    crawler_service_base_url: str = ""
    crawler_service_timeout_seconds: float = 30.0
    crawler_job_timeout_seconds: float = 3600.0
    crawler_job_poll_interval_seconds: float = 5.0
    # Crawler와 동일한 다운로드 루트: 재수집 중복 파일만 안전하게 정리한다.
    crawler_staging_dir: str = str(PROJECT_ROOT / "test_documents" / "lh_downloads")

    # Host-accessible mirror of the Document Worker output root.
    pipeline_output_host_path: str = ""

    # CollectionRun retention: disabled | dry_run | delete
    collection_retention_mode: Literal[
        "disabled",
        "dry_run",
        "delete",
    ] = "disabled"
    collection_retention_output_root: str = str(
        PROJECT_ROOT / "outputs"
    )

    # Optional one-time mapping for paths stored by an older deployment.
    # Both stored/access values for a path type must be configured together.
    collection_retention_legacy_document_stored_root: str = ""
    collection_retention_legacy_document_access_root: str = ""
    collection_retention_legacy_output_stored_root: str = ""
    collection_retention_legacy_output_access_root: str = ""

    # Admin authentication
    admin_id: str = ""
    admin_password: str = ""
    admin_jwt_secret: str = ""
    admin_jwt_expire_seconds: int = 3600
    admin_cookie_name: str = "admin_access_token"
    admin_cookie_secure: bool = False
    admin_cookie_samesite: str = "lax"

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

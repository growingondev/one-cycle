from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGSettings(BaseSettings):
    """
    RAG Service 환경설정.

    로컬/AWS Host:
        프로젝트 루트의 .env 파일을 읽는다.

    Docker:
        컨테이너에 주입된 환경변수가 .env 값보다 우선한다.
    """

    # PostgreSQL
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # Embedding Service
    embedding_service_url: str = "http://127.0.0.1:18001"

    embedding_model_name: str = "BAAI/bge-m3"
    embedding_model_path: str = "BAAI/bge-m3"

    # llama.cpp
    llama_base_url: str = "http://127.0.0.1:8080"
    llama_model: str

    llama_temperature: float = 0.0
    llama_top_p: float = 1.0
    llama_max_tokens: int = 1024
    llama_timeout_seconds: int = 180
    llama_context_top_k: int = 5
    llama_max_context_chars: int = 6000

    # RAG
    rag_db_top_k: int = 5

    # MVP
    mvp_document_format: str = "hwpx"
    mvp_announcement_id: int | None = None

    @field_validator(
        "mvp_announcement_id",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(
        cls,
        value,
    ):
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = RAGSettings()

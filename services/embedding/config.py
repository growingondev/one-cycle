from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingSettings(BaseSettings):
    """
    Embedding Service 환경설정.

    로컬/AWS Host:
        프로젝트 루트의 .env 파일을 읽는다.

    Docker:
        컨테이너에 주입된 환경변수가 .env 값보다 우선한다.
    """

    embedding_model_name: str = "BAAI/bge-m3"
    embedding_model_path: str = "BAAI/bge-m3"

    embedding_use_fp16: bool = True
    embedding_require_cuda: bool = True
    embedding_device_index: int = 0

    embedding_service_url: str = "http://127.0.0.1:18001"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = EmbeddingSettings()

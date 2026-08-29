from __future__ import annotations

import os

import httpx
import numpy as np


class EmbeddingClientError(RuntimeError):
    """Embedding Service 호출 중 발생하는 오류."""


class EmbeddingClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv(
                "EMBEDDING_SERVICE_URL",
                "http://127.0.0.1:18001",
            )
        ).rstrip("/")

        self.timeout_seconds = timeout_seconds

    def embed_query(self, query: str) -> np.ndarray:
        query = query.strip()

        if not query:
            raise EmbeddingClientError(
                "검색 질문이 비어 있습니다."
            )

        try:
            response = httpx.post(
                f"{self.base_url}/v1/embeddings",
                json={
                    "items": [
                        {
                            "id": "query",
                            "text": query,
                        }
                    ]
                },
                timeout=self.timeout_seconds,
            )

        except httpx.RequestError as exc:
            raise EmbeddingClientError(
                f"Embedding Service 연결 실패: {exc}"
            ) from exc

        if response.status_code != 200:
            try:
                payload = response.json()
            except ValueError:
                payload = {}

            error = payload.get("error") or {}

            code = error.get(
                "code",
                "EMBEDDING_SERVICE_ERROR",
            )
            message = error.get(
                "message",
                response.text,
            )

            raise EmbeddingClientError(
                f"{code}: {message}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingClientError(
                "Embedding Service 응답이 JSON 형식이 아닙니다."
            ) from exc

        if payload.get("model") != "BAAI/bge-m3":
            raise EmbeddingClientError(
                f"예상하지 못한 임베딩 모델입니다: {payload.get('model')}"
            )

        if payload.get("dimension") != 1024:
            raise EmbeddingClientError(
                f"임베딩 차원이 1024가 아닙니다: {payload.get('dimension')}"
            )

        if payload.get("normalized") is not True:
            raise EmbeddingClientError(
                "Embedding Service 응답 벡터가 normalized=true가 아닙니다."
            )

        items = payload.get("items")

        if not isinstance(items, list):
            raise EmbeddingClientError(
                "Embedding Service 응답 items가 올바르지 않습니다."
            )

        matched = [
            item
            for item in items
            if item.get("id") == "query"
        ]

        if len(matched) != 1:
            raise EmbeddingClientError(
                "Embedding Service 응답에서 query id를 정확히 하나 찾지 못했습니다."
            )

        vector = np.asarray(
            matched[0].get("embedding"),
            dtype=np.float32,
        )

        if vector.shape != (1024,):
            raise EmbeddingClientError(
                f"질문 임베딩 shape 오류: {vector.shape}"
            )

        if not np.isfinite(vector).all():
            raise EmbeddingClientError(
                "질문 임베딩에 NaN/Infinity가 있습니다."
            )

        return vector
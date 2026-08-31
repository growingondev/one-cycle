from __future__ import annotations

import os

import httpx
import numpy as np


class EmbeddingClientError(RuntimeError):
    """Embedding Service 호출 중 발생하는 오류."""


class EmbeddingClient:
    """
    공용 Embedding Service HTTP Client.

    RAG에서는 embed_query()를 사용하고,
    Document Worker에서는 embed_items()를 사용한다.

    실제 BGE-M3 모델은 이 Client에서 직접 실행하지 않는다.
    모든 Embedding 생성은 POST /v1/embeddings API를 통해 요청한다.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv(
                "EMBEDDING_SERVICE_URL",
                "http://127.0.0.1:18001",
            )
        ).rstrip("/")

        self.timeout_seconds = timeout_seconds

    # ============================================================
    # 여러 Item Embedding
    # ============================================================

    def embed_items(
        self,
        items: list[dict[str, str]],
    ) -> dict[str, np.ndarray]:
        """
        여러 텍스트를 Embedding Service에 전달하고
        ID별 Dense Vector를 반환한다.

        Request 예시:

        {
            "items": [
                {
                    "id": "chunk-001",
                    "text": "임베딩할 텍스트"
                }
            ]
        }

        반환 예시:

        {
            "chunk-001": np.ndarray(shape=(1024,))
        }

        응답 배열 순서에는 의존하지 않고,
        반드시 item.id 기준으로 결과를 매칭한다.
        """

        # --------------------------------------------------------
        # 1. Request 검증
        # --------------------------------------------------------

        if not items:
            raise EmbeddingClientError(
                "Embedding 요청 items가 비어 있습니다."
            )

        request_ids: list[str] = []

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise EmbeddingClientError(
                    f"items[{index}]가 객체가 아닙니다."
                )

            item_id = str(
                item.get("id") or ""
            ).strip()

            text = str(
                item.get("text") or ""
            ).strip()

            if not item_id:
                raise EmbeddingClientError(
                    f"items[{index}].id가 비어 있습니다."
                )

            if not text:
                raise EmbeddingClientError(
                    f"items[{index}].text가 비어 있습니다."
                )

            request_ids.append(
                item_id
            )

        if len(request_ids) != len(
            set(request_ids)
        ):
            raise EmbeddingClientError(
                "Embedding 요청 id가 중복되었습니다."
            )

        # --------------------------------------------------------
        # 2. Embedding Service HTTP 호출
        # --------------------------------------------------------

        try:
            response = httpx.post(
                (
                    f"{self.base_url}"
                    "/v1/embeddings"
                ),
                json={
                    "items": items,
                },
                timeout=self.timeout_seconds,
            )

        except httpx.TimeoutException as exc:
            raise EmbeddingClientError(
                "Embedding Service 요청 시간이 초과되었습니다."
            ) from exc

        except httpx.RequestError as exc:
            raise EmbeddingClientError(
                "Embedding Service 연결 실패: "
                f"{exc}"
            ) from exc

        # --------------------------------------------------------
        # 3. HTTP Error Response 처리
        # --------------------------------------------------------

        if response.status_code != 200:
            try:
                payload = response.json()

            except ValueError:
                payload = {}

            error = (
                payload.get("error")
                or {}
            )

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

        # --------------------------------------------------------
        # 4. JSON Response 파싱
        # --------------------------------------------------------

        try:
            payload = response.json()

        except ValueError as exc:
            raise EmbeddingClientError(
                "Embedding Service 응답이 "
                "JSON 형식이 아닙니다."
            ) from exc

        # --------------------------------------------------------
        # 5. Embedding 기본 규격 검증
        # --------------------------------------------------------

        if (
            payload.get("model")
            != "BAAI/bge-m3"
        ):
            raise EmbeddingClientError(
                "예상하지 못한 임베딩 모델입니다: "
                f"{payload.get('model')}"
            )

        if (
            payload.get("dimension")
            != 1024
        ):
            raise EmbeddingClientError(
                "임베딩 차원이 1024가 아닙니다: "
                f"{payload.get('dimension')}"
            )

        if (
            payload.get("normalized")
            is not True
        ):
            raise EmbeddingClientError(
                "Embedding Service 응답 벡터가 "
                "normalized=true가 아닙니다."
            )

        # --------------------------------------------------------
        # 6. Response Items 검증
        # --------------------------------------------------------

        response_items = (
            payload.get("items")
        )

        if not isinstance(
            response_items,
            list,
        ):
            raise EmbeddingClientError(
                "Embedding Service 응답 items가 "
                "올바르지 않습니다."
            )

        result: dict[
            str,
            np.ndarray,
        ] = {}

        for index, item in enumerate(
            response_items
        ):
            if not isinstance(
                item,
                dict,
            ):
                raise EmbeddingClientError(
                    "Embedding Service 응답의 "
                    f"items[{index}]가 객체가 아닙니다."
                )

            item_id = str(
                item.get("id")
                or ""
            ).strip()

            if not item_id:
                raise EmbeddingClientError(
                    "Embedding Service 응답에 "
                    "id가 없는 item이 있습니다."
                )

            if item_id in result:
                raise EmbeddingClientError(
                    "Embedding Service 응답 id가 "
                    f"중복되었습니다: {item_id}"
                )

            # ----------------------------------------------------
            # Vector 변환
            # ----------------------------------------------------

            try:
                vector = np.asarray(
                    item.get(
                        "embedding"
                    ),
                    dtype=np.float32,
                )

            except (
                TypeError,
                ValueError,
            ) as exc:
                raise EmbeddingClientError(
                    "Embedding Vector를 "
                    "float32 배열로 변환하지 "
                    f"못했습니다: {item_id}"
                ) from exc

            # ----------------------------------------------------
            # Vector Shape 검증
            # ----------------------------------------------------

            if vector.shape != (
                1024,
            ):
                raise EmbeddingClientError(
                    "Embedding shape이 "
                    "올바르지 않습니다. "
                    f"id={item_id}, "
                    f"shape={vector.shape}"
                )

            # ----------------------------------------------------
            # NaN / Infinity 검증
            # ----------------------------------------------------

            if not np.isfinite(
                vector
            ).all():
                raise EmbeddingClientError(
                    "Embedding에 NaN 또는 "
                    "Infinity가 있습니다. "
                    f"id={item_id}"
                )

            result[item_id] = (
                vector
            )

        # --------------------------------------------------------
        # 7. Request ID ↔ Response ID 검증
        # --------------------------------------------------------

        request_id_set = set(
            request_ids
        )

        response_id_set = set(
            result.keys()
        )

        missing_ids = (
            request_id_set
            - response_id_set
        )

        extra_ids = (
            response_id_set
            - request_id_set
        )

        if missing_ids:
            raise EmbeddingClientError(
                "Embedding 응답에서 "
                "누락된 id가 있습니다: "
                f"{sorted(missing_ids)}"
            )

        if extra_ids:
            raise EmbeddingClientError(
                "Embedding 응답에 "
                "요청하지 않은 id가 있습니다: "
                f"{sorted(extra_ids)}"
            )

        # --------------------------------------------------------
        # 8. ID → Vector Mapping 반환
        # --------------------------------------------------------

        return result

    # ============================================================
    # RAG Query Embedding
    # ============================================================

    def embed_query(
        self,
        query: str,
    ) -> np.ndarray:
        """
        RAG 검색 질문 한 건을 임베딩한다.

        기존 RAG가 사용하는 공개 Method는 유지하고,
        내부적으로 공용 embed_items()를 사용한다.
        """

        query = query.strip()

        if not query:
            raise EmbeddingClientError(
                "검색 질문이 비어 있습니다."
            )

        result = self.embed_items(
            [
                {
                    "id": "query",
                    "text": query,
                }
            ]
        )

        return result["query"]
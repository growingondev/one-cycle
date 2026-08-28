from __future__ import annotations

from pipeline.embedding.config import (
    BATCH_SIZE,
    DEVICE_INDEX,
    MAX_LENGTH,
    MODEL_NAME,
    MODEL_PATH,
    NORMALIZE_EMBEDDINGS,
    REQUIRE_CUDA,
    USE_FP16,
)
from pipeline.embedding.embedding_generator import generate_embeddings
from pipeline.embedding.model_loader import (
    LoadedEmbeddingModel,
    load_bge_m3_model,
)
from pipeline.embedding.models import EmbeddingItem

from services.embedding.schemas import (
    EmbeddingRequestItem,
    EmbeddingResponse,
    EmbeddingResponseItem,
)


class EmbeddingService:
    def __init__(self) -> None:
        self._loaded_model: LoadedEmbeddingModel | None = None

    @property
    def is_ready(self) -> bool:
        return self._loaded_model is not None

    @property
    def model_name(self) -> str | None:
        if self._loaded_model is None:
            return None

        return self._loaded_model.runtime.model_name

    def load_model(self) -> None:
        if self._loaded_model is not None:
            return

        self._loaded_model = load_bge_m3_model(
            model_name=MODEL_NAME,
            model_path=MODEL_PATH,
            use_fp16=USE_FP16,
            require_cuda=REQUIRE_CUDA,
            device_index=DEVICE_INDEX,
        )

    def unload_model(self) -> None:
        self._loaded_model = None

    def create_embeddings(
        self,
        request_items: list[EmbeddingRequestItem],
    ) -> EmbeddingResponse:
        if self._loaded_model is None:
            raise RuntimeError("Embedding model is not loaded.")

        embedding_items = [
            EmbeddingItem(
                chunk_id=item.id,
                embedding_text=item.text,
                metadata={},
            )
            for item in request_items
        ]

        generated = generate_embeddings(
            self._loaded_model,
            embedding_items,
            batch_size=BATCH_SIZE,
            max_length=MAX_LENGTH,
            normalize_embeddings=NORMALIZE_EMBEDDINGS,
        )

        response_items = [
            EmbeddingResponseItem(
                id=request_item.id,
                embedding=vector.tolist(),
            )
            for request_item, vector in zip(
                request_items,
                generated.vectors,
                strict=True,
            )
        ]

        return EmbeddingResponse(
            model=self._loaded_model.runtime.model_name,
            dimension=generated.dimension,
            normalized=generated.normalized,
            items=response_items,
        )
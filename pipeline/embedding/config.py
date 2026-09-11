from __future__ import annotations

from services.embedding.config import settings


MODEL_NAME = settings.embedding_model_name
MODEL_PATH = settings.embedding_model_path

TEXT_FIELD = "embedding_text"

BATCH_SIZE = 8
MAX_LENGTH = 8192

USE_FP16 = settings.embedding_use_fp16
REQUIRE_CUDA = settings.embedding_require_cuda
DEVICE_INDEX = settings.embedding_device_index

NORMALIZE_EMBEDDINGS = True

EMBEDDINGS_FILENAME = "embeddings.npy"
METADATA_FILENAME = "metadata.json"
REPORT_FILENAME = "embedding_report.json"

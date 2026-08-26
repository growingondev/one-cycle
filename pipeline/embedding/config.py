from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME",
    "BAAI/bge-m3",
).strip()

MODEL_PATH = os.getenv(
    "EMBEDDING_MODEL_PATH",
    MODEL_NAME,
).strip()

TEXT_FIELD = "embedding_text"

BATCH_SIZE = 8
MAX_LENGTH = 8192

USE_FP16 = _env_bool(
    "EMBEDDING_USE_FP16",
    True,
)

REQUIRE_CUDA = _env_bool(
    "EMBEDDING_REQUIRE_CUDA",
    True,
)

DEVICE_INDEX = int(
    os.getenv(
        "EMBEDDING_DEVICE_INDEX",
        "0",
    )
)

NORMALIZE_EMBEDDINGS = True

EMBEDDINGS_FILENAME = "embeddings.npy"
METADATA_FILENAME = "metadata.json"
REPORT_FILENAME = "embedding_report.json"

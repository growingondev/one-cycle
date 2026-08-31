FROM nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    EMBEDDING_MODEL_NAME=BAAI/bge-m3 \
    EMBEDDING_MODEL_PATH=/models/bge-m3 \
    EMBEDDING_USE_FP16=true \
    EMBEDDING_REQUIRE_CUDA=true \
    EMBEDDING_DEVICE_INDEX=0

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        curl \
        python3.12 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY docker/embedding/requirements.txt /tmp/requirements.txt
RUN python3.12 -m pip install --no-cache-dir --break-system-packages \
        --requirement /tmp/requirements.txt

COPY services/__init__.py /app/services/__init__.py
COPY services/embedding /app/services/embedding
COPY pipeline/__init__.py /app/pipeline/__init__.py
COPY pipeline/embedding /app/pipeline/embedding

EXPOSE 18001

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:18001/health || exit 1

CMD ["python3.12", "-m", "uvicorn", "services.embedding.main:app", "--host", "0.0.0.0", "--port", "18001"]

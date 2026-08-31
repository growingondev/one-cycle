FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    POSTGRES_HOST=postgres \
    POSTGRES_PORT=5432 \
    EMBEDDING_SERVICE_URL=http://embedding:18001 \
    LLAMA_BASE_URL=http://llm:8080

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY docker/rag/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements.txt

COPY services/__init__.py /app/services/__init__.py
COPY services/rag /app/services/rag
COPY services/embedding/__init__.py /app/services/embedding/__init__.py
COPY services/embedding/client.py /app/services/embedding/client.py
COPY services/embedding/config.py /app/services/embedding/config.py
COPY rag /app/rag

EXPOSE 18002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:18002/health || exit 1

CMD ["python", "-m", "uvicorn", "services.rag.main:app", "--host", "0.0.0.0", "--port", "18002"]

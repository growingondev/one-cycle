# Embedding / RAG / LLM Docker 전달사항

이 문서는 전체 Compose를 수정하지 않고 세 서비스의 build/run 계약만 정리한다.
모든 build context는 프로젝트 루트(`one-cycle_api`)이다.

## Embedding

- Dockerfile: `docker/embedding/Dockerfile`
- requirements: `docker/embedding/requirements.txt`
- port: `18001`
- 실행 module: `services.embedding.main:app`
- GPU: NVIDIA Container Toolkit 및 GPU device 필요
- model volume: host의 BGE-M3 디렉터리 → `/models/bge-m3:ro`

필수/지원 환경변수:

```env
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_MODEL_PATH=/models/bge-m3
EMBEDDING_USE_FP16=true
EMBEDDING_REQUIRE_CUDA=true
EMBEDDING_DEVICE_INDEX=0
```

단독 검증 예시:

```bash
docker build --platform linux/amd64 -f docker/embedding/Dockerfile -t one-cycle-embedding:test .
docker run --rm --gpus all -p 18001:18001 \
  -v /home/ubuntu/ddokbot/models/embedding/bge-m3:/models/bge-m3:ro \
  one-cycle-embedding:test
curl http://127.0.0.1:18001/health
curl -X POST http://127.0.0.1:18001/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"id":"smoke-1","text":"임베딩 테스트"}]}'
docker run --rm --gpus all --entrypoint python3.12 one-cycle-embedding:test \
  -c 'import torch; from FlagEmbedding import BGEM3FlagModel; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())'
```

Compose healthcheck URL은 `http://127.0.0.1:18001/health`이며 start period는 모델 로드 시간을 고려해야 한다.

## RAG

- Dockerfile: `docker/rag/Dockerfile`
- requirements: `docker/rag/requirements.txt`
- port: `18002`
- 실행 module: `services.rag.main:app`
- GPU/model volume: 불필요
- dependencies: `postgres`, `embedding`, `llm`

환경변수:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=one_cycle
POSTGRES_USER=one_cycle
POSTGRES_PASSWORD=CHANGE_ME
EMBEDDING_SERVICE_URL=http://embedding:18001
LLAMA_BASE_URL=http://llm:8080
LLAMA_MODEL=gemma
LLAMA_TEMPERATURE=0.0
LLAMA_TOP_P=1.0
LLAMA_MAX_TOKENS=1024
LLAMA_TIMEOUT_SECONDS=180
LLAMA_CONTEXT_TOP_K=5
LLAMA_MAX_CONTEXT_CHARS=6000
RAG_DB_TOP_K=5
MVP_DOCUMENT_FORMAT=hwpx
MVP_ANNOUNCEMENT_ID=
```

`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `LLAMA_MODEL`은 설정상 필수다.
`MVP_ANNOUNCEMENT_ID`는 생략하거나 빈 문자열로 주입할 수 있다.

단독 import/health 검증 예시(외부 연결은 health 요청 시 사용하지 않음):

```bash
docker build --platform linux/amd64 -f docker/rag/Dockerfile -t one-cycle-rag:test .
docker run --rm -p 18002:18002 \
  -e POSTGRES_DB=one_cycle -e POSTGRES_USER=one_cycle \
  -e POSTGRES_PASSWORD=test -e LLAMA_MODEL=gemma \
  one-cycle-rag:test
curl http://127.0.0.1:18002/health
docker run --rm --entrypoint python one-cycle-rag:test \
  -c 'import services.rag.main, rag.retrieval; print("rag imports: ok")'
```

실제 `/v1/rag/answer` 검증에는 pgvector schema/data, Embedding, LLM 세 dependency가 모두 필요하다.

## LLM (llama.cpp)

- Dockerfile: `docker/llm/Dockerfile`
- port: `8080`
- GPU: NVIDIA Container Toolkit 및 GPU device 필요
- model volume: host의 GGUF 디렉터리 → `/models:ro`
- entrypoint: `docker/llm/entrypoint.sh`가 env를 `llama-server` option으로 변환
- env 전달: `.env` → Compose `env_file` 또는 `docker run --env-file` → entrypoint

환경변수:

```env
LLM_MODEL_PATH=/models/gemma-4-12B-it-Q4_0.gguf
LLM_MODEL_ALIAS=gemma
LLM_HOST=0.0.0.0
LLM_PORT=8080
LLM_CTX_SIZE=4096
LLM_GPU_LAYERS=all
LLM_PARALLEL=1
LLM_THREADS=4
LLM_THREADS_BATCH=4
LLM_REASONING=off
```

위 10개 변수는 모두 필수다. Dockerfile에는 기본값이 없으며, unset 또는 빈 문자열이면 entrypoint가
해당 변수명을 출력하고 `llama-server` 실행 전에 종료한다. Dockerfile은 `.env`를 이미지에 복사하지 않는다.

AWS에 설치된 llama.cpp의 commit/tag가 기록되어 있지 않다. 최초 운영 build 전에 해당 값을 확인하고
`--build-arg LLAMA_CPP_REF=<검증된-tag>`로 고정해야 한다. 기본값은 `master`이므로 재현 가능한 운영 이미지에는 그대로 사용하지 않는다.

단독 검증 예시:

```bash
docker build --platform linux/amd64 -f docker/llm/Dockerfile \
  --build-arg LLAMA_CPP_REF=<검증된-tag> -t one-cycle-llm:test .
docker run --rm --gpus all -p 8080:8080 \
  --env-file /path/to/llm.env \
  -v /home/ubuntu/ddokbot/models/llm/gemma4-12b:/models:ro \
  one-cycle-llm:test
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/v1/models
curl -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemma","messages":[{"role":"user","content":"한 문장으로 인사해 주세요."}],"temperature":0,"max_tokens":128}'
```

## 현재 검증 범위

작성 환경은 Apple Silicon(`arm64`)이고 Docker daemon이 실행되지 않아 실제 image build/container 실행은
수행하지 못했다. Python 및 shell 구문, Docker build context 경로, RAG의 직접 GPU import 제거를 정적으로
검증했다. RAG requirements는 별도 Python 3.12 가상환경에 실제 설치했으며, runtime import와 FastAPI
`GET /health` TestClient 응답 `200 {"status":"ok"}`를 확인했다. CUDA/GPU, 모델 load, 실제 네트워크 API
요청은 위 명령으로 AWS NVIDIA L4에서 최종 확인해야 한다.

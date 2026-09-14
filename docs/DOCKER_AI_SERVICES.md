# Docker AI Services

> 기준 브랜치: `main`  
> 기준 구현: `infra/docker-compose.yml`, `infra/embedding/`, `infra/rag/`, `infra/llm/`  
> 이 문서는 DDOK BOT의 AI 영역인 Embedding Service, RAG Service, llama.cpp LLM Service가 Docker에서 어떻게 분리되고 연결되는지 설명한다.

---

## 1. 개요

DDOK BOT의 AI 기능은 하나의 컨테이너에 모두 넣지 않고 기능별 Service로 분리한다.

```text
Embedding Service
RAG Service
LLM Service
```

Docker Compose에서는 세 Service에 모두 `ai` profile이 적용되어 있다.

```text
profiles: ["ai"]
```

전체 연결 구조는 다음과 같다.

```text
Backend
  ↓
RAG Service :18002
  ├─ PostgreSQL + pgvector :5432
  ├─ Embedding Service :18001
  └─ LLM Service :8080
```

RAG Service가 AI 질의응답의 중심이며, 질문 임베딩이 필요할 때 Embedding Service를 호출하고 답변 생성이 필요할 때 LLM Service를 호출한다.

---

## 2. Docker 관련 디렉터리

현재 AI Docker 설정은 `infra/` 아래에 위치한다.

```text
infra/
├── docker-compose.yml
├── embedding/
│   └── Dockerfile
├── rag/
│   ├── Dockerfile
│   └── requirements.txt
└── llm/
    ├── Dockerfile
    └── entrypoint.sh
```

서비스 코드 자체는 Docker 디렉터리에 두지 않는다.

```text
services/embedding/
services/rag/
rag/
pipeline/embedding/
```

Dockerfile은 필요한 서비스 코드를 Image 내부 `/app`으로 복사해 실행한다.

---

## 3. AI Service 포트

현재 Docker Compose 기준 포트는 다음과 같다.

| Service | Container Port | Host Binding |
|---|---:|---|
| Embedding | `18001` | `127.0.0.1:18001` |
| RAG | `18002` | `127.0.0.1:18002` |
| LLM | `8080` | `127.0.0.1:8080` |
| PostgreSQL | `5432` | `127.0.0.1:${POSTGRES_PORT:-5432}` |

AI Service 포트가 모두 `127.0.0.1`에 바인딩되어 있기 때문에 Host에서 직접 접근할 수 있지만 외부 네트워크에 그대로 공개하는 구조는 아니다.

---

# Embedding Service

## 4. Embedding Container 역할

Embedding Container는 BGE-M3 모델을 GPU에 로드하고 Embedding API를 제공한다.

```text
Chunk / Query Text
  ↓
Embedding Service
  ↓
BAAI/bge-m3
  ↓
1024차원 Dense Vector
```

Docker Service 이름:

```text
embedding
```

Container 이름:

```text
one-cycle-embedding
```

Image 이름:

```text
one-cycle-embedding:dev
```

---

## 5. Embedding Dockerfile

파일:

```text
infra/embedding/Dockerfile
```

Base Image:

```text
nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04
```

Python:

```text
Python 3.12
```

GPU 기반 Embedding을 위해 CUDA Runtime Image를 사용한다.

주요 기본 환경설정:

```text
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_MODEL_PATH=/models/bge-m3
EMBEDDING_USE_FP16=true
EMBEDDING_REQUIRE_CUDA=true
EMBEDDING_DEVICE_INDEX=0
```

---

## 6. Embedding Service 실제 실행 진입점

Docker에서 Embedding Service를 실행하는 명령은 다음과 같다.

```text
python3.12 -m uvicorn
services.embedding.main:app
--host 0.0.0.0
--port 18001
```

따라서 **실제 서비스 실행 진입점은 `services/embedding/main.py`**다.

```text
Docker
  ↓
services.embedding.main:app
  ↓
EmbeddingService
  ↓
BGE-M3
```

`pipeline/embedding/run_embeddings.py`를 Docker Service 진입점으로 실행하는 구조가 아니다.

`pipeline/embedding`의 공통 Embedding 구현은 Service 내부에서 재사용될 수 있지만, HTTP Service 자체의 진입점은 `services/embedding/main.py`다.

---

## 7. Embedding 모델 Mount

Host에 저장된 BGE-M3 모델을 Container 내부에 Read Only로 Mount한다.

Docker Compose:

```text
Host
${EMBEDDING_MODEL_HOST_PATH:-../models/embedding/bge-m3}

        ↓ mount

Container
/models/bge-m3
```

Container 내부 환경변수:

```text
EMBEDDING_MODEL_PATH=/models/bge-m3
```

따라서 Image 안에 모델 파일을 직접 포함하지 않는다.

장점:

```text
Image 크기 감소
모델과 Application Image 분리
모델 교체 시 Image 재빌드 최소화
```

---

## 8. Embedding GPU

Docker Compose에서:

```text
gpus: all
```

을 설정한다.

Embedding Container 내부에서는:

```text
EMBEDDING_REQUIRE_CUDA=true
EMBEDDING_DEVICE_INDEX=0
```

을 사용한다.

즉 Container가 Host NVIDIA GPU를 사용할 수 있도록 연결하고 BGE-M3 연산을 GPU에서 수행하는 구조다.

---

## 9. Embedding Health Check

Embedding Container는 다음 Endpoint를 검사한다.

```http
GET http://127.0.0.1:18001/health
```

Health Check 설정:

```text
interval     = 30s
timeout      = 5s
start_period = 180s
retries      = 5
```

Embedding 모델 로딩 시간이 필요할 수 있으므로 시작 유예 시간이 길게 설정되어 있다.

---

# LLM Service

## 10. LLM Container 역할

LLM Container는 llama.cpp의 `llama-server`를 실행한다.

```text
RAG Prompt
  ↓ HTTP
LLM Service
  ↓
llama-server
  ↓
GGUF Model
  ↓
Generated Answer
```

Docker Service 이름:

```text
llm
```

Container 이름:

```text
one-cycle-llm
```

Image:

```text
one-cycle-llm:dev
```

---

## 11. llama.cpp Docker Build

파일:

```text
infra/llm/Dockerfile
```

LLM Dockerfile은 Multi-stage Build를 사용한다.

```text
Builder Stage
  ↓
llama.cpp Source Clone
  ↓
CUDA ON Build
  ↓
llama-server Binary 생성

Runtime Stage
  ↓
llama-server Binary만 복사
  ↓
실제 서버 실행
```

Builder Base:

```text
nvidia/cuda:13.0.2-devel-ubuntu24.04
```

Runtime Base:

```text
nvidia/cuda:13.0.2-runtime-ubuntu24.04
```

---

## 12. llama.cpp CUDA Build

Builder에서 llama.cpp를 Clone한 뒤 CMake로 Build한다.

핵심 설정:

```text
-DGGML_CUDA=ON
-DLLAMA_CURL=OFF
-DBUILD_SHARED_LIBS=OFF
-DCMAKE_BUILD_TYPE=Release
```

실제 Build Target:

```text
llama-server
```

즉 GPU 추론이 가능한 llama-server Binary를 만든다.

---

## 13. llama.cpp 버전 지정

Docker Build Argument:

```text
LLAMA_CPP_REF
```

Compose 기본값:

```text
master
```

Dockerfile에서는:

```text
git fetch origin "${LLAMA_CPP_REF}"
git checkout --detach FETCH_HEAD
```

방식으로 해당 llama.cpp Ref를 Build한다.

필요한 경우 `.env`에서 특정 Commit이나 Ref를 지정할 수 있다.

---

## 14. LLM 모델 Mount

GGUF 모델 역시 Docker Image 내부에 포함하지 않고 Host에서 Mount한다.

```text
Host
${LLM_MODEL_HOST_PATH:-../models/llm}

        ↓ mount

Container
/models
```

기본 모델 파일:

```text
gemma-4-12B-it-Q4_0.gguf
```

Container에서 사용하는 실제 경로:

```text
/models/${LLM_MODEL_FILE}
```

기본값 기준:

```text
/models/gemma-4-12B-it-Q4_0.gguf
```

---

## 15. LLM 주요 환경변수

현재 Docker Compose 기본값:

```text
LLM_MODEL_PATH
= /models/${LLM_MODEL_FILE:-gemma-4-12B-it-Q4_0.gguf}

LLM_MODEL_ALIAS
= gemma

LLM_HOST
= 0.0.0.0

LLM_PORT
= 8080

LLM_CTX_SIZE
= 4096

LLM_GPU_LAYERS
= all

LLM_PARALLEL
= 1

LLM_THREADS
= 4

LLM_THREADS_BATCH
= 4
```

또한 현재 Compose에는 다음 설정도 전달된다.

```text
LLM_REASONING
LLM_REASONING_BUDGET
```

기본값:

```text
LLM_REASONING=on
LLM_REASONING_BUDGET=256
```

실제 운영값은 `.env`에서 덮어쓸 수 있다.

---

## 16. LLM `entrypoint.sh`

실제 llama-server 실행 명령은 Dockerfile에 길게 작성하지 않고 다음 파일에서 조립한다.

```text
infra/llm/entrypoint.sh
```

먼저 필요한 환경변수가 모두 존재하는지 검사한다.

또한:

```text
LLM_MODEL_PATH
```

에 실제 GGUF 파일이 존재하는지 확인한다.

파일이 없으면 Container를 정상 실행하지 않는다.

---

## 17. 실제 llama-server 실행 형태

`entrypoint.sh`는 환경변수를 다음 llama-server Option으로 변환한다.

```text
LLM_MODEL_PATH
→ --model

LLM_MODEL_ALIAS
→ --alias

LLM_HOST
→ --host

LLM_PORT
→ --port

LLM_CTX_SIZE
→ --ctx-size

LLM_GPU_LAYERS
→ --n-gpu-layers

LLM_PARALLEL
→ --parallel

LLM_THREADS
→ --threads

LLM_THREADS_BATCH
→ --threads-batch

LLM_REASONING
→ --reasoning

LLM_REASONING_BUDGET
→ --reasoning-budget
```

마지막으로:

```text
--no-ui
```

옵션을 추가해 서버를 실행한다.

---

## 18. `entrypoint.sh`가 필요한 이유

Docker Compose는 **설정값을 환경변수로 전달하는 역할**을 한다.

```text
docker-compose.yml
  ↓
환경변수
  ↓
entrypoint.sh
  ↓
llama-server 실행 옵션
```

즉 Compose에:

```text
LLM_CTX_SIZE=4096
```

라고 적는 것만으로 llama.cpp가 자동으로 이 값을 사용하는 것이 아니다.

`entrypoint.sh`가 이 값을:

```text
--ctx-size 4096
```

형태로 변환해서 실제 `llama-server` 실행 명령에 넣는다.

따라서 두 파일의 역할은 다르다.

```text
docker-compose.yml
= 어떤 설정값을 사용할지 결정

entrypoint.sh
= 설정값으로 llama-server 명령을 구성
```

---

## 19. LLM GPU

Docker Compose:

```text
gpus: all
```

llama.cpp Build:

```text
GGML_CUDA=ON
```

실행:

```text
LLM_GPU_LAYERS=all
```

의 조합으로 GPU 추론을 사용한다.

개념적으로:

```text
NVIDIA Driver
  ↓
Docker GPU 연결
  ↓
CUDA Runtime
  ↓
llama.cpp CUDA Backend
  ↓
GPU Model Inference
```

구조다.

---

## 20. LLM Health Check

LLM Container는:

```http
GET http://127.0.0.1:${LLM_PORT}/health
```

를 검사한다.

기본 포트:

```text
8080
```

Health Check:

```text
interval     = 30s
timeout      = 5s
start_period = 180s
retries      = 5
```

대형 GGUF 모델의 GPU Load 시간을 고려해 시작 유예 시간이 설정되어 있다.

---

# RAG Service

## 21. RAG Container 역할

RAG Container는 질문을 받아 Retrieval과 Generation 전체 흐름을 조정한다.

Docker Service:

```text
rag
```

Container:

```text
one-cycle-rag
```

Image:

```text
one-cycle-rag:dev
```

RAG Container 자체가 Embedding 모델이나 LLM 모델을 직접 로드하지 않는다.

```text
RAG
├─ Query Embedding → Embedding Service
├─ Retrieval → PostgreSQL + pgvector / BM25
└─ Generation → LLM Service
```

구조다.

---

## 22. RAG Dockerfile

파일:

```text
infra/rag/Dockerfile
```

Base Image:

```text
python:3.12.13-slim
```

RAG Service에는 CUDA Runtime이 필요하지 않다.

GPU 연산이 필요한 Embedding과 LLM이 별도 Container로 분리되어 있기 때문이다.

---

## 23. RAG Service 실행 진입점

Docker CMD:

```text
python -m uvicorn
services.rag.main:app
--host 0.0.0.0
--port 18002
```

따라서 실제 RAG Service 진입점:

```text
services/rag/main.py
```

Endpoint:

```text
GET  /health
POST /v1/rag/answer
```

---

## 24. RAG Container 내부 연결 주소

Docker Compose에서는 Container끼리 Host의 `localhost`로 통신하지 않는다.

Docker Service 이름을 DNS 이름처럼 사용한다.

현재 RAG 환경:

```text
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

EMBEDDING_SERVICE_URL=http://embedding:18001

LLAMA_BASE_URL=http://llm:8080
```

구조:

```text
rag
├─ postgres:5432
├─ embedding:18001
└─ llm:8080
```

---

## 25. 왜 Docker에서는 `127.0.0.1`을 사용하지 않는가

각 Container는 독립된 Network Namespace를 가진다.

따라서 RAG Container에서:

```text
127.0.0.1:18001
```

은 Embedding Container가 아니라 **RAG Container 자신**을 의미한다.

Docker Compose에서는:

```text
http://embedding:18001
```

처럼 Service 이름을 사용한다.

반대로 Host에서 직접 접근할 때는:

```text
http://127.0.0.1:18001
```

을 사용할 수 있다.

---

## 26. RAG `depends_on`

RAG는 다음 Service에 의존한다.

```text
postgres
embedding
llm
```

Compose 설정:

```text
postgres
→ service_healthy

embedding
→ service_healthy

llm
→ service_healthy
```

즉 RAG Container는 의존 Service의 Health Check 성공을 기준으로 시작 순서를 조정한다.

---

# AI Profile

## 27. `profiles: ["ai"]`

현재:

```text
embedding
llm
rag
```

세 Service에는:

```text
profiles: ["ai"]
```

가 지정되어 있다.

따라서 일반적인 Compose 실행과 AI Service 실행을 분리할 수 있다.

AI Profile을 활성화할 때는 개념적으로:

```bash
docker compose --profile ai up
```

형태로 실행한다.

---

## 28. AI Service 의존 관계

현재 전체 의존 관계를 AI 영역 중심으로 보면:

```text
PostgreSQL
    │
    ├──────────────┐
    │              │
Embedding         LLM
    │              │
    └──────┬───────┘
           ↓
          RAG
           ↓
        Backend
```

실제 요청 방향은:

```text
Backend
  ↓
RAG
  ├→ PostgreSQL
  ├→ Embedding
  └→ LLM
```

이다.

---

# Host 실행과 Docker 실행

## 29. Host에서 직접 실행할 때

개발 중 Docker를 사용하지 않고 각 Service를 직접 실행할 수도 있다.

이 경우 같은 Host에서 실행되므로 일반적으로 Loopback 주소를 사용한다.

예:

```text
Embedding
http://127.0.0.1:<embedding-port>

RAG
http://127.0.0.1:<rag-port>

LLM
http://127.0.0.1:<llm-port>
```

실제 개발용 Port를 Docker 기본 Port와 다르게 사용할 경우 `.env`의 Service URL을 해당 Port에 맞춰 변경해야 한다.

---

## 30. Docker에서 실행할 때

Docker 내부 통신은 Service DNS를 사용한다.

```text
Embedding
http://embedding:18001

RAG
http://rag:18002

LLM
http://llm:8080

PostgreSQL
postgres:5432
```

Docker Compose의 `environment` 값이 `.env`의 Loopback 값을 덮어써 Container 내부에서 올바른 주소를 사용하게 한다.

---

## 31. `.env`와 Compose 환경변수

Compose에서는:

```text
env_file:
  - ../.env
```

를 사용한다.

따라서 기본 설정은 프로젝트 `.env`에서 읽는다.

동시에 `environment:`에 같은 변수가 있으면 Compose에서 지정한 값이 Container에 전달된다.

예:

```text
.env

EMBEDDING_SERVICE_URL=http://127.0.0.1:18001
```

이어도 RAG Container에는 Compose 설정에 의해:

```text
EMBEDDING_SERVICE_URL=http://embedding:18001
```

이 전달된다.

따라서:

```text
Host 개발
→ .env의 127.0.0.1 주소

Docker
→ Compose의 Service DNS 주소
```

로 같은 코드를 실행할 수 있다.

---

# 모델과 Image 분리

## 32. 모델을 Docker Image에 포함하지 않는 이유

Embedding 모델과 GGUF LLM 모델은 모두 Volume Mount 방식이다.

```text
Application Image
≠
Model File
```

Embedding:

```text
Host bge-m3
→ /models/bge-m3
```

LLM:

```text
Host GGUF
→ /models
```

이 구조는 모델 파일이 큰 AI 서비스에서 Image 크기를 줄이고 모델 변경을 쉽게 한다.

---

# Build Context

## 33. AI Service Build Context

현재 Compose에서 AI Service의 Build Context는 모두 프로젝트 Root다.

```text
context: ..
```

Docker Compose 파일 위치가:

```text
infra/docker-compose.yml
```

이므로 `..`은 Repository Root를 의미한다.

예:

```text
repository root
├── services/
├── pipeline/
├── rag/
└── infra/
```

이렇게 해야 Dockerfile에서 서비스 코드와 공통 Pipeline 코드를 Image에 복사할 수 있다.

---

# 주요 파일 관계

## 34. Embedding

```text
infra/embedding/Dockerfile
  ↓
services/embedding/
  ↓
pipeline/embedding/
  ↓
BAAI/bge-m3
```

---

## 35. RAG

```text
infra/rag/Dockerfile
  ↓
services/rag/
  ↓
rag/
  ├─ retrieval/
  └─ generation/
```

RAG Image에는 Embedding 모델 전체를 넣지 않고 Embedding HTTP Client에 필요한 코드만 포함한다.

---

## 36. LLM

```text
infra/llm/Dockerfile
  ↓
llama.cpp Build
  ↓
llama-server
  ↓
infra/llm/entrypoint.sh
  ↓
Mounted GGUF Model
```

---

# 핵심 정리

## 37. 최종 구조

```text
                   Docker Compose
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ↓                ↓                ↓
   Embedding            RAG              LLM
    :18001             :18002           :8080
        │                │                │
        │                ├───────────────→│
        │                │   Generation   │
        │                │                │
        └───────────────→│                │
          Query Vector   │                │
                         │
                         ↓
                  PostgreSQL + pgvector
                       :5432
```

현재 AI Docker 구성의 핵심은 다음과 같다.

```text
Embedding Service
- GPU 사용
- BGE-M3
- 실제 진입점: services/embedding/main.py
- Port 18001

RAG Service
- Retrieval + Generation Orchestration
- 실제 진입점: services/rag/main.py
- Embedding / PostgreSQL / LLM 연결
- Port 18002

LLM Service
- GPU 사용
- llama.cpp
- GGUF Model
- entrypoint.sh에서 실행 Option 구성
- Port 8080

Container 내부 연결
- postgres:5432
- embedding:18001
- llm:8080
- rag:18002

Host 접근
- 127.0.0.1:<published port>
```

즉 Docker 환경에서는 **Embedding, RAG, LLM을 각각 독립 Service로 분리하고, RAG가 Embedding과 LLM을 HTTP로 연결하는 구조**다.

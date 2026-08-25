# DDOKBOT Environment

> 이 문서는 DDOKBOT 프로젝트의 실행 환경과 환경변수 구조를 설명합니다.
>
> 새로운 개발자 또는 AI가 다음 내용을 이해할 수 있도록 작성되었습니다.
>
> - 프로젝트 Root와 Python 환경
> - Backend / Frontend 실행 Port
> - PostgreSQL 및 pgvector 환경
> - GPU / CUDA / BGE-M3 환경
> - llama.cpp / LLM Generation 환경
> - `.env`와 `.env.example`의 역할
> - 주요 환경변수의 의미
> - 개발 서버를 실제로 실행하는 순서
> - SSH Port Forwarding 방식
>
> 실제 비밀번호, JWT Secret, DB Password 등의 Secret 값은 이 문서에 기록하지 않습니다.

---

# 1. Project Root

AWS 개발 서버 기준 프로젝트 Root:

```text
/home/ubuntu/ddokbot/one-cycle
```

대부분의 Backend/Pipeline 명령은 이 위치에서 실행합니다.

```bash
cd /home/ubuntu/ddokbot/one-cycle
```

---

# 2. Python Environment

현재 Backend 및 Pipeline 실행에 사용한 Python 가상환경:

```text
/home/ubuntu/ddokbot/venvs/one-cycle-backend
```

Python 실행 파일:

```text
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python
```

가상환경 활성화:

```bash
source /home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/activate
```

또는 가상환경을 활성화하지 않고 직접 실행할 수 있습니다.

```bash
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python
```

---

# 3. PYTHONPATH

프로젝트 내부 Module Import를 안정적으로 사용하기 위해
프로젝트 Root에서 다음 형태로 실행합니다.

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python ...
```

예:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m backend.app.services.pipeline_persistence
```

---

# 4. Python Dependencies

Root Python dependency 파일:

```text
requirements.txt
```

현재 주요 dependency 영역:

```text
FastAPI
Pydantic Settings
Uvicorn
SQLAlchemy
psycopg
Alembic
pgvector

JPype1

FlagEmbedding
NumPy
Transformers
Accelerate
Safetensors
SentencePiece
PyTorch
CUDA Toolkit
Triton
```

Frontend dependency는 별도로 관리합니다.

```text
frontend/user/package.json
```

---

# 5. Environment Files

실제 환경 설정:

```text
.env
```

Template:

```text
.env.example
```

역할:

```text
.env
→ 실제 Runtime 값

.env.example
→ 필요한 환경변수 이름과 예제 값
```

---

# 6. Secret 관리 원칙

다음 값은 README나 Source Code에 실제 값을 기록하지 않습니다.

```text
DB Password
ADMIN_PASSWORD
ADMIN_JWT_SECRET
Private API Key
Private SSH Key
```

`.env.example`에는 변수명과 안전한 예제만 넣습니다.

예:

```env
ADMIN_PASSWORD=change-me
ADMIN_JWT_SECRET=change-me
```

---

# 7. .env Loading

Backend 설정:

```text
backend/app/core/config.py
```

현재 Pydantic Settings가 Project Root의:

```text
.env
```

를 읽도록 구성되어 있습니다.

개념:

```text
/home/ubuntu/ddokbot/one-cycle/.env
                ↓
backend/app/core/config.py
                ↓
Backend Settings
```

---

# 8. os.getenv를 직접 사용하는 영역

모든 환경변수가 Pydantic Settings를 거치는 것은 아닙니다.

현재 다음 코드에서는 `os.getenv()`를 직접 사용합니다.

```text
backend/app/services/chat_service.py
backend/app/services/admin_auth_service.py
backend/app/services/pipeline_gateway.py

rag/db_pipeline.py
rag/service.py

pipeline/parser/common.py
```

따라서 환경변수 문제를 확인할 때 `core/config.py`만 보면 안 됩니다.

---

# 9. Backend Port

현재 개발 기준 FastAPI Port:

```text
8000
```

Backend 실행:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m uvicorn backend.app.main:app \
--host 127.0.0.1 \
--port 8000
```

정상 URL:

```text
http://127.0.0.1:8000
```

---

# 10. Backend Health Check

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

DB:

```bash
curl -i \
http://127.0.0.1:8000/api/health/db
```

---

# 11. User Frontend Port

User Frontend:

```text
frontend/user/
```

Vite 개발 Port:

```text
5173
```

실행:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run dev
```

현재 `package.json` Script:

```text
vite --host 0.0.0.0
```

---

# 12. User Frontend API Base

파일:

```text
frontend/user/src/config.ts
```

현재:

```typescript
export const API_BASE_URL = "/api";
```

Browser는 FastAPI `8000`을 직접 호출하지 않습니다.

```text
Browser
 ↓
Vite :5173
 ↓
/api
 ↓
FastAPI :8000
```

구조입니다.

---

# 13. Vite Proxy

실제 Proxy 설정:

```text
frontend/user/vite.config.ts
```

Frontend API 문제가 발생하면 이 파일을 확인합니다.

개념:

```text
/api/*
   ↓
http://127.0.0.1:8000/api/*
```

---

# 14. Admin Frontend

Admin Frontend:

```text
frontend/admin/
```

실행 파일:

```text
frontend/admin/serve_admin.py
```

Admin UI는 React/Vite가 아니라:

```text
HTML
CSS
JavaScript
Python Proxy Server
```

구조입니다.

---

# 15. Admin API Backend Target

Admin Frontend도 API Base:

```text
/api
```

를 사용합니다.

`serve_admin.py`가 해당 요청을 FastAPI로 Proxy합니다.

현재 Backend Target 기준:

```text
127.0.0.1:8000
```

입니다.

과거 코드나 문서에서:

```text
18000
```

이 발견되면 Legacy 값인지 확인합니다.

---

# 16. PostgreSQL

Database:

```text
PostgreSQL
```

Vector Extension:

```text
pgvector
```

Infrastructure:

```text
infra/docker-compose.yml
```

pgvector 초기화:

```text
infra/postgres/init/01-enable-vector.sql
```

---

# 17. PostgreSQL 연결 구조

```text
.env
 ↓
Backend Settings
 ↓
backend/app/db/session.py
 ↓
SQLAlchemy
 ↓
psycopg
 ↓
PostgreSQL
```

---

# 18. Database 환경변수

DB 관련 정확한 변수명은:

```text
backend/app/core/config.py
.env.example
```

를 최종 기준으로 사용합니다.

새로운 개발자는 `.env.example`을 복사하여 `.env`를 작성하는 방식을 권장합니다.

예:

```bash
cp .env.example .env
```

그 후 실제 환경에 맞게 값을 설정합니다.

---

# 19. Database Connection Test

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from sqlalchemy import text
from backend.app.db.session import engine

with engine.connect() as conn:
    result = conn.execute(
        text("SELECT 1")
    ).scalar_one()

print("[OK] DB:", result)
PY
```

정상:

```text
[OK] DB: 1
```

---

# 20. pgvector 확인

PostgreSQL에서 pgvector Extension이 활성화되어 있어야 합니다.

SQL 개념:

```sql
SELECT extname
FROM pg_extension
WHERE extname = 'vector';
```

결과에:

```text
vector
```

가 있어야 합니다.

---

# 21. Alembic Environment

Alembic 설정:

```text
alembic.ini
```

Migration:

```text
migrations/
```

Migration 적용:

```bash
cd /home/ubuntu/ddokbot/one-cycle

alembic upgrade head
```

가상환경 Alembic을 명시하려면:

```bash
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/alembic \
upgrade head
```

---

# 22. Embedding Environment

현재 Embedding Model은 BGE-M3를 사용합니다.

기본 Model:

```text
BAAI/bge-m3
```

Model Loading:

```text
pipeline/embedding/model_loader.py
```

Embedding 설정:

```text
pipeline/embedding/config.py
```

사용 영역:

```text
Document Embedding
pipeline/embedding/

Query Embedding
rag/retrieval/query_embedding.py
```

Embedding Runtime 설정은 `.env` 환경변수에서 읽습니다.

현재 사용하는 환경변수:

```env
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_DEVICE_INDEX=0
EMBEDDING_REQUIRE_CUDA=true
EMBEDDING_USE_FP16=true
```

연결 구조:

```text
.env
  ↓
pipeline/embedding/config.py
  ↓
pipeline/embedding/model_loader.py
  ├─ Document Embedding
  └─ Query Embedding
```

각 환경변수의 역할:

| 환경변수 | 역할 |
|---|---|
| `EMBEDDING_MODEL_NAME` | 사용할 Embedding Model |
| `EMBEDDING_DEVICE_INDEX` | 사용할 CUDA Device Index |
| `EMBEDDING_REQUIRE_CUDA` | CUDA 필수 여부 |
| `EMBEDDING_USE_FP16` | FP16 사용 여부 |

현재 검증된 Runtime 값:

```text
Model
BAAI/bge-m3

Device Index
0

CUDA Required
True

FP16
True
```

따라서 Embedding Model 또는 GPU 실행 설정을 변경할 때
`pipeline/embedding/config.py`의 값을 직접 수정하는 것이 아니라
우선 `.env`의 해당 환경변수를 변경합니다.

코드의 기본값과 실제 Runtime 값이 다를 수 있으므로
실행 환경에서는 `.env`와 Runtime 출력을 최종 기준으로 확인합니다.

---

# 24. CUDA Environment

현재 검증된 환경 예:

```text
CUDA
13.0 계열

PyTorch
CUDA 지원 Build
```

Root `requirements.txt`에는 검증된 프로젝트 dependency version이 기록되어 있습니다.

GPU 환경은 AWS Instance와 CUDA Driver에 따라 달라질 수 있으므로
무조건 다른 서버에 같은 CUDA Package를 설치하지 않습니다.

---

# 25. CUDA 확인

```bash
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
import torch

print("torch:", torch.__version__)
print("cuda:", torch.version.cuda)
print("available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
PY
```

정상 예:

```text
available: True
device: NVIDIA L4
```

---

# 26. BGE-M3 Model 확인

Query Embedding이나 Pipeline Embedding을 실행하면 다음 성격의 로그가 나타납니다.

```text
BGE-M3 모델 로드

모델: BAAI/bge-m3
장치: cuda:0
CUDA 사용: True
FP16 사용: True
```

이 단계에서 실패하면 RAG DB SQL이나 Frontend를 수정할 문제가 아닙니다.

먼저:

```text
PyTorch
CUDA
FlagEmbedding
Model Download
GPU Memory
```

를 확인합니다.

---

# 27. Embedding Dimension

현재:

```text
1024
```

입니다.

이 값은 서로 일치해야 합니다.

```text
Document Embedding
Query Embedding
DB pgvector Dimension
RAG Retrieval SQL
```

한 부분만 변경하면 안 됩니다.

---

# 28. RAG Environment Variables

현재 RAG 실행과 Backend-RAG 연결에 사용되는 주요 환경변수:

```text
RAG_ANSWER_FUNCTION
RAG_DB_TOP_K
MVP_ANNOUNCEMENT_ID
MVP_DOCUMENT_FORMAT
```

각 환경변수의 사용 위치:

| 환경변수 | 사용 위치 | 역할 |
|---|---|---|
| `RAG_ANSWER_FUNCTION` | `backend/app/services/chat_service.py` | Backend에서 호출할 RAG 진입 함수 |
| `RAG_DB_TOP_K` | `rag/db_pipeline.py` | pgvector 검색 결과 수 |
| `MVP_ANNOUNCEMENT_ID` | `rag/service.py` | MVP에서 허용할 공고 ID 제한 |
| `MVP_DOCUMENT_FORMAT` | `rag/db_pipeline.py` | Generation에 전달할 대표 문서 형식 |

현재 설정 예:

```env
RAG_ANSWER_FUNCTION=rag.service:answer_question
RAG_DB_TOP_K=5
MVP_ANNOUNCEMENT_ID=1
MVP_DOCUMENT_FORMAT=hwpx
```

전체 연결 구조:

```text
.env
  │
  ├─ RAG_ANSWER_FUNCTION
  │       ↓
  │  backend/app/services/chat_service.py
  │       ↓
  │  rag.service:answer_question
  │
  ├─ MVP_ANNOUNCEMENT_ID
  │       ↓
  │  rag/service.py
  │
  ├─ RAG_DB_TOP_K
  │       ↓
  │  rag/db_pipeline.py
  │
  └─ MVP_DOCUMENT_FORMAT
          ↓
     rag/db_pipeline.py
```

환경변수의 실제 동작과 기본값은 각 사용 코드가 최종 기준입니다.

---

# 29. RAG_ANSWER_FUNCTION

Backend와 RAG 진입점을 연결합니다.

현재:

```env
RAG_ANSWER_FUNCTION=rag.service:answer_question
```

연결:

```text
backend/app/services/chat_service.py
        ↓
RAG_ANSWER_FUNCTION
        ↓
rag.service:answer_question
```

이 값이 잘못되면 Chat Service가 RAG Function을 Import하지 못합니다.

---

# 30. RAG_DB_TOP_K

DB pgvector Retrieval에서 반환할 검색 결과 수를 설정합니다.

현재 기본값은 실제:

```text
rag/db_pipeline.py
```

를 최종 기준으로 확인합니다.

현재 개발 과정에서는 Top-K 5 결과를 사용하는 구조를 확인했습니다.

예:

```env
RAG_DB_TOP_K=5
```

---

# 31. MVP_ANNOUNCEMENT_ID

현재 MVP에서 특정 공고만 지원하도록 제한할 때 사용됩니다.

관련 코드:

```text
rag/service.py
```

예:

```env
MVP_ANNOUNCEMENT_ID=1
```

이 값이 설정되어 있고 사용자가 다른 Announcement ID를 요청하면:

```text
현재 MVP에서 지원하지 않는 공고입니다.
```

형태의 응답이 반환될 수 있습니다.

---

# 32. MVP_DOCUMENT_FORMAT

Generation에 전달하는 대표 문서 Format을 설정할 때 사용됩니다.

현재 코드 위치:

```text
rag/db_pipeline.py
```

예:

```env
MVP_DOCUMENT_FORMAT=hwpx
```

현재 MVP 구조의 임시 설정 성격이 있으므로 향후 Document별 Format을 DB에서 정확히 전달하는 구조로 개선할 수 있습니다.

---

# 33. Generation Runtime

현재 Generation은:

```text
llama.cpp
+
GGUF 기반 LLM
```

구조입니다.

FastAPI가 직접 Model을 로딩하는 것이 아니라 별도의 llama.cpp Server를 HTTP로 호출합니다.

Generation 코드는 특정 LLM에 종속되지 않도록 구성되어 있으며, llama.cpp에서 실행할 GGUF Model과 Model Alias를 변경하여 Gemma, Qwen 등 여러 LLM을 교체하여 사용할 수 있습니다.

현재 성능 테스트에서는 Gemma 계열 GGUF Model을 사용하고 있습니다.

---

# 34. Generation 연결 구조

```text
rag/generation/generator.py
       ↓
rag/generation/llm_client.py
       ↓
HTTP
       ↓
POST /v1/chat/completions
       ↓
llama.cpp Server
       ↓
현재 실행 중인 GGUF LLM
```

Generation Client는 특정 Model 이름을 Source Code에 고정하지 않습니다.

실제 호출할 Model 이름은 `LLAMA_MODEL` 환경변수에서 결정됩니다.

---

# 35. llama.cpp Endpoint

Generation 설정:

```text
rag/generation/config.py
```

현재 코드에서 사용하는 기본 구조:

```text
LLAMA_BASE_URL
+
/v1/chat/completions
```

현재 개발 기준 Local Endpoint:

```text
http://127.0.0.1:8080
```

실제 Runtime 값은 환경변수:

```text
LLAMA_BASE_URL
```

에서 결정됩니다.

Generation 설정의 Source of Truth:

```text
rag/generation/config.py
.env
.env.example
```

---

# 36. llama.cpp Port

Generation Server 개발 기준:

```text
8080
```

개념:

```text
FastAPI :8000
    ↓
RAG
    ↓
llama.cpp :8080
```

Frontend Browser가 `8080`을 직접 호출하지 않습니다.

Local PC에서 AWS llama.cpp Server를 직접 테스트할 경우 SSH Port Forwarding을 사용할 수 있습니다.

예:

```bash
ssh -i <PEM_FILE_PATH> \
-L 8080:127.0.0.1:8080 \
ubuntu@<AWS_PUBLIC_IP>
```

---

# 37. LLM Model

Generation에서 사용할 실제 LLM GGUF 파일은 프로젝트 Source Code와 분리하여 관리합니다.

현재 Gemma 성능 테스트에서 확인한 Model Path 예:

```text
/home/ubuntu/ddokbot/models/llm/gemma4-12b/gemma-4-12B-it-Q4_0.gguf
```

Model Binary를 프로젝트 Source Code 폴더 안에 복사하지 않는 것이 좋습니다.

llama.cpp Server 실행 시 실제 GGUF 경로와 별도로 Model Alias를 지정합니다.

예:

```bash
./build/bin/llama-server \
  -m /home/ubuntu/ddokbot/models/llm/gemma4-12b/gemma-4-12B-it-Q4_0.gguf \
  --alias gemma \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 8192 \
  --n-gpu-layers all \
  --no-ui
```

이 경우 RAG Runtime의 환경변수는 다음과 같이 맞춥니다.

```env
LLAMA_MODEL=gemma
```

핵심 규칙:

```text
llama-server --alias 값
=
LLAMA_MODEL 값
```

예:

```text
Gemma
--alias gemma
LLAMA_MODEL=gemma

Qwen
--alias qwen
LLAMA_MODEL=qwen

다른 LLM
--alias <model-alias>
LLAMA_MODEL=<model-alias>
```

따라서 성능 테스트 과정에서 LLM이 변경되어도 Python Generation Source Code의 Model 이름을 직접 수정하지 않습니다.

변경 대상은:

```text
1. llama-server의 GGUF Model 경로
2. llama-server의 --alias
3. LLAMA_MODEL 환경변수
```

입니다.

> **현재 미사용 환경변수**
>
> `.env` 및 `.env.example`에 다음 Key가 존재하지만,
> 현재 확인된 Python Runtime 코드에서는 직접 참조되지 않습니다.
>
> ```text
> LLAMA_API_KEY
> MVP_ANNOUNCEMENT_DIRECTORY
> ```
>
> 따라서 이 두 값은 현재 실행에 필수인 환경변수로 간주하지 않습니다.
> 향후 코드에서 다시 사용할 수 있으므로 삭제 여부는 별도로 결정합니다.
>
> 환경변수 사용 여부를 다시 확인하려면:
>
> ```bash
> grep -RHnE \
> 'LLAMA_API_KEY|MVP_ANNOUNCEMENT_DIRECTORY' \
> backend rag pipeline config run_pipeline.py \
> --include='*.py' \
> --exclude-dir='__pycache__'
> ```

---

# 38. Generation Config

Generation 설정 파일:

```text
rag/generation/config.py
```

현재 Generation은 별도로 실행되는 llama.cpp Server를 사용하며,
FastAPI/RAG Process는 HTTP를 통해 해당 Server를 호출합니다.

특정 LLM 이름과 주요 Generation Parameter를 Source Code에 고정하지 않고 환경변수로 관리할 수 있도록 구성되어 있습니다.

현재 사용하는 주요 환경변수:

```env
LLAMA_BASE_URL=http://127.0.0.1:8080
LLAMA_MODEL=gemma
LLAMA_TIMEOUT_SECONDS=600
LLAMA_TEMPERATURE=0.0
LLAMA_TOP_P=1.0
LLAMA_MAX_TOKENS=1024
LLAMA_CONTEXT_TOP_K=5
LLAMA_MAX_CONTEXT_CHARS=6000
```

각 환경변수의 역할:

| 환경변수 | 역할 |
|---|---|
| `LLAMA_BASE_URL` | llama.cpp Server 주소 |
| `LLAMA_MODEL` | Chat Completion 요청에 전달할 llama.cpp Model Alias |
| `LLAMA_TIMEOUT_SECONDS` | llama.cpp HTTP 요청 Timeout |
| `LLAMA_TEMPERATURE` | LLM 답변 생성 Temperature |
| `LLAMA_TOP_P` | LLM Top-P Sampling 값 |
| `LLAMA_MAX_TOKENS` | LLM이 한 응답에서 생성할 최대 Token 수 |
| `LLAMA_CONTEXT_TOP_K` | Generation Context에 전달할 최대 Retrieval 결과 수 |
| `LLAMA_MAX_CONTEXT_CHARS` | LLM에 전달할 Retrieval 근거의 전체 최대 문자 수 |

연결 구조:

```text
.env
  ↓
rag/generation/config.py
  ↓
GenerationConfig
  ↓
rag/generation/llm_client.py
  ↓
POST /v1/chat/completions
  ↓
llama.cpp Server
  ↓
LLAMA_MODEL과 일치하는 Model Alias
  ↓
현재 실행 중인 GGUF LLM
```

현재 Gemma 성능 테스트 기준 Runtime 설정:

```text
Base URL
http://127.0.0.1:8080

Model Alias
gemma

Temperature
0.0

Top-P
1.0

Max Output Tokens
1024

Context Top-K
5

Max Retrieval Context Characters
6000

Timeout
600 seconds
```

`LLAMA_MAX_CONTEXT_CHARS`는 각 Chunk마다 6000자를 허용한다는 의미가 아닙니다.

Generation에 전달되는 Retrieval 근거 전체에 대해 최대 문자 수를 제한합니다.

예:

```text
LLAMA_CONTEXT_TOP_K=5
LLAMA_MAX_CONTEXT_CHARS=6000
```

이면 Retrieval 결과는 최대 5개까지 후보로 사용할 수 있지만,
실제 Prompt에 전달되는 근거 Content의 전체 길이는 최대 약 6000자를 기준으로 제한합니다.

현재 Generation 설정 구조:

```text
.env
│
├─ LLAMA_BASE_URL
├─ LLAMA_MODEL
├─ LLAMA_TIMEOUT_SECONDS
│
├─ LLAMA_TEMPERATURE
├─ LLAMA_TOP_P
├─ LLAMA_MAX_TOKENS
│
├─ LLAMA_CONTEXT_TOP_K
└─ LLAMA_MAX_CONTEXT_CHARS
        ↓
rag/generation/config.py
        ↓
GenerationConfig
```

따라서 Model 또는 Generation Parameter를 변경할 때 `rag/generation/config.py`의 값을 직접 수정하는 방식보다 환경변수를 변경하는 방식을 사용합니다.

`rag/generation/config.py`에는 환경변수가 없을 때 사용할 일부 기본값과 설정 검증 로직이 존재하지만,
`LLAMA_MODEL`은 특정 LLM을 기본값으로 고정하지 않습니다.

실행 전에 사용할 Model Alias를 명시적으로 설정해야 합니다.

---

# 39. LLM Server 확인

Generation 실패 시 FastAPI보다 먼저 llama.cpp Server가 살아 있는지 확인합니다.

예:

```bash
curl -i \
http://127.0.0.1:8080/v1/models
```

현재 Gemma Server가 `--alias gemma`로 실행된 경우 응답의 Model ID에서 다음 값을 확인할 수 있습니다.

```text
"id": "gemma"
```

이 값과:

```env
LLAMA_MODEL=gemma
```

가 일치해야 합니다.

Generation Client가 사용하는 정확한 Endpoint 및 설정:

```text
rag/generation/config.py
rag/generation/llm_client.py
```

를 확인합니다.

---

# 40. Chat Completions Endpoint

현재 Generation Client는 OpenAI 호환 형태의:

```text
POST /v1/chat/completions
```

를 호출합니다.

개념 Payload:

```json
{
  "model": "gemma",
  "messages": [],
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 1024,
  "stream": false
}
```

실제 `model`, `temperature`, `top_p`, `max_tokens` 값은 `GenerationConfig`와 Runtime 환경변수에서 결정됩니다.

정확한 Payload 생성 코드는:

```text
rag/generation/llm_client.py
```

를 확인합니다.

---

# 41. Generation Timeout

llama.cpp가 느리거나 응답하지 않을 경우 Timeout이 발생할 수 있습니다.

설정:

```text
rag/generation/config.py
```

Timeout 문제와 Retrieval 문제를 구분해야 합니다.

Evidence는 정상 검색됐는데 Generation만 실패하면 llama.cpp Runtime도 확인합니다.

---

# 42. Admin Environment Variables

현재 관리자 인증 Service에서 확인된 환경변수:

```text
ADMIN_ID
ADMIN_PASSWORD

ADMIN_JWT_SECRET
ADMIN_JWT_EXPIRE_SECONDS

ADMIN_COOKIE_SECURE
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SAMESITE
```

---

# 43. ADMIN_ID / ADMIN_PASSWORD

관리자 로그인 Credential입니다.

실제 값은:

```text
.env
```

에서 관리합니다.

Source Code나 문서에 실제 Credential을 기록하지 않습니다.

---

# 44. ADMIN_JWT_SECRET

관리자 JWT 서명 Secret입니다.

다음처럼 안전하지 않은 고정값을 운영에 사용하지 않습니다.

```text
secret
1234
admin
```

실제 운영 값은 충분히 긴 Random Secret을 사용합니다.

---

# 45. ADMIN_JWT_EXPIRE_SECONDS

관리자 인증 Token 유효기간입니다.

현재 코드 기본값 예:

```text
3600
```

즉 기본적으로 1시간을 의미할 수 있습니다.

실제 동작은:

```text
backend/app/services/admin_auth_service.py
```

를 확인합니다.

---

# 46. Cookie Environment

관리자 인증 Cookie 관련 변수:

```text
ADMIN_COOKIE_SECURE
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SAMESITE
```

HTTPS 배포 환경과 Local 개발 환경의 Cookie 설정이 다를 수 있습니다.

---

# 47. Pipeline Gateway Environment

파일:

```text
backend/app/services/pipeline_gateway.py
```

환경변수에 저장된 함수 경로를 사용하여 Pipeline 구현을 호출할 수 있습니다.

정확한 환경변수 이름은 해당 파일을 Source of Truth로 사용합니다.

Pipeline 기능을 교체할 때 Route 자체보다 Gateway 연결을 먼저 확인합니다.

---

# 48. Parser Environment

파일:

```text
pipeline/parser/common.py
```

Parser의 외부 Library/JAR Path 등에 환경변수를 사용할 수 있습니다.

정확한 변수명:

```text
pipeline/parser/common.py
```

을 확인합니다.

---

# 49. Java / JPype Environment

HWP/HWPX Parsing 과정에서 Java Library를 사용할 수 있으므로:

```text
Java Runtime
JPype1
Parser JAR
```

가 필요할 수 있습니다.

Parser Library 위치:

```text
pipeline/parser/libs/hwp/
pipeline/parser/libs/hwpx/
```

관련 문제가 발생하면 Python Parser 코드뿐 아니라 Java Runtime도 확인합니다.

---

# 50. Node.js Environment

User Frontend는 Node/npm 환경이 필요합니다.

확인:

```bash
node --version
npm --version
```

Frontend Dependency 설치:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm install
```

Build:

```bash
npm run build
```

---

# 51. Frontend node_modules

경로:

```text
frontend/user/node_modules/
```

이 디렉터리는 Dependency 설치 결과입니다.

Source Code가 아닙니다.

필요하면:

```bash
npm install
```

로 다시 생성할 수 있습니다.

---

# 52. Local Browser에서 AWS Vite 확인

로컬 PC에서:

```bash
ssh -i <PEM_FILE_PATH> \
-L 5173:127.0.0.1:5173 \
ubuntu@<AWS_PUBLIC_IP>
```

그 후 Browser:

```text
http://127.0.0.1:5173
```

---

# 53. Frontend + Backend Port Forwarding

Backend도 직접 확인하고 싶으면:

```bash
ssh -i <PEM_FILE_PATH> \
-L 5173:127.0.0.1:5173 \
-L 8000:127.0.0.1:8000 \
ubuntu@<AWS_PUBLIC_IP>
```

로컬:

```text
Frontend
http://127.0.0.1:5173

Backend
http://127.0.0.1:8000
```

---

# 54. llama.cpp까지 Local에서 확인해야 할 경우

필요한 경우:

```bash
ssh -i <PEM_FILE_PATH> \
-L 5173:127.0.0.1:5173 \
-L 8000:127.0.0.1:8000 \
-L 8080:127.0.0.1:8080 \
ubuntu@<AWS_PUBLIC_IP>
```

그러면 로컬에서 llama.cpp Endpoint도 확인할 수 있습니다.

일반 사용자는 이 Port가 필요하지 않습니다.

---

# 55. 개발 환경 전체 Port

현재 개발 기준:

| 서비스 | Port |
|---|---:|
| User Frontend / Vite | `5173` |
| FastAPI Backend | `8000` |
| llama.cpp Generation | `8080` |
| PostgreSQL | 실제 Infra 설정 확인 |

PostgreSQL Port는:

```text
infra/docker-compose.yml
.env
```

을 최종 기준으로 확인합니다.

---

# 56. 전체 Runtime Architecture

```text
Local Browser
      │
      │ SSH Tunnel
      ▼
AWS Vite :5173
      │
      │ /api
      ▼
FastAPI :8000
      │
      ├───────────────────┐
      │                   │
      ▼                   ▼
PostgreSQL             RAG
 + pgvector              │
                         ▼
                  llama.cpp :8080
                         │
                         ▼
                  GGUF 기반 LLM
               (Gemma / Qwen 등)
```

---

# 57. Backend 시작 순서

권장 개발 시작 순서:

```text
1. PostgreSQL
2. llama.cpp
3. FastAPI
4. User Frontend
5. SSH Tunnel
6. Browser
```

---

# 58. PostgreSQL 확인

먼저 DB가 준비되어 있는지 확인합니다.

```bash
curl -i \
http://127.0.0.1:8000/api/health/db
```

단 Backend가 아직 실행되지 않았다면 직접 SQLAlchemy Test를 사용합니다.

---

# 59. llama.cpp 확인

Generation 기능을 사용할 경우 llama.cpp Server를 먼저 실행합니다.

현재 구조에서는 사용할 Model에 따라 GGUF 파일 경로와 `--alias`를 지정합니다.

예:

```bash
./build/bin/llama-server \
  -m <GGUF_MODEL_PATH> \
  --alias <MODEL_ALIAS> \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 8192 \
  --n-gpu-layers all \
  --no-ui
```

실행 후:

```bash
curl http://127.0.0.1:8080/v1/models
```

로 실제 Model Alias를 확인합니다.

응답의 Model ID와:

```text
LLAMA_MODEL
```

환경변수 값이 동일해야 합니다.

`--ctx-size`는 llama.cpp Server가 한 요청에서 사용할 수 있는 전체 Context 크기입니다.

반면:

```text
LLAMA_MAX_TOKENS
```

는 LLM이 생성할 최대 출력 Token 수이며,

```text
LLAMA_MAX_CONTEXT_CHARS
```

는 RAG에서 LLM Prompt에 전달할 Retrieval 근거 길이를 제한하는 설정입니다.

세 값은 서로 다른 역할을 가지므로 구분하여 관리합니다.

Source Code 기준 연결 정보:

```text
rag/generation/config.py
rag/generation/llm_client.py
```

---

# 60. FastAPI 시작

```bash
cd /home/ubuntu/ddokbot/one-cycle

set -a
source .env
set +a

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m uvicorn backend.app.main:app \
--host 127.0.0.1 \
--port 8000
```

`set -a`는 `.env`에 정의된 변수를 Shell 환경으로 export할 필요가 있을 때 사용합니다.

Pydantic Settings만 사용하는 변수는 `.env`를 직접 읽을 수 있지만,
현재 일부 코드가 `os.getenv()`를 직접 사용하므로 Shell export 여부를 확인하는 것이 안전합니다.

---

# 61. User Frontend 시작

다른 Terminal:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run dev
```

---

# 62. 전체 서비스 Smoke Test

Backend:

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

DB:

```bash
curl -i \
http://127.0.0.1:8000/api/health/db
```

공고:

```bash
curl -i \
http://127.0.0.1:8000/api/announcements
```

Chat:

```bash
curl -i \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{"announcementId":1,"question":"신청 일정은 언제인가?"}'
```

Frontend:

```text
http://127.0.0.1:5173
```

---

# 63. Environment Troubleshooting

## ModuleNotFoundError

확인:

```text
현재 Working Directory
PYTHONPATH
Python Interpreter
가상환경
```

권장:

```bash
cd /home/ubuntu/ddokbot/one-cycle
export PYTHONPATH=.
```

---

## DB Authentication Failed

예:

```text
password authentication failed
```

확인:

```text
.env
PostgreSQL User
Password
Database
Host
Port
```

RAG 코드를 수정하지 않습니다.

---

## CUDA Not Available

확인:

```bash
nvidia-smi
```

Python:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

---

## BGE-M3 Model Load Failed

확인:

```text
FlagEmbedding
Transformers
Model Cache
GPU Memory
CUDA
Model Name
```

---

## llama.cpp Connection Refused

확인:

```text
llama.cpp Process
Port 8080
rag/generation/config.py
```

---

## HTTP 500 Chat

Backend Terminal의 Traceback을 확인합니다.

가능성:

```text
Query Embedding
DB Retrieval
Generation
LLM
Validation
```

---

## Browser Failed to Fetch

확인:

```text
Vite 실행 여부
Vite Proxy
FastAPI 실행 여부
SSH Tunnel
Browser Network
```

---

# 64. .env.example 관리 원칙

새 환경변수를 코드에 추가하면:

```text
.env.example
```

에도 반드시 추가합니다.

예:

```env
NEW_SETTING=example-value
```

단 실제 Secret은 넣지 않습니다.

---

# 65. 환경변수 삭제 원칙

코드에서 더 이상 사용하지 않는 환경변수를 삭제할 때:

```text
1. 전체 grep
2. Dynamic Import/Gateway 확인
3. .env 삭제
4. .env.example 삭제
5. docs 수정
6. Runtime Test
```

순서로 진행합니다.

---

# 66. 환경변수 Reference 확인

예:

```bash
cd /home/ubuntu/ddokbot/one-cycle

grep -RHnE \
'os\.getenv|os\.environ|BaseSettings|env_file' \
backend rag pipeline config \
--include='*.py' \
--exclude-dir='__pycache__'
```

이 결과가 현재 Runtime 환경변수의 가장 중요한 확인 자료 중 하나입니다.

---

# 67. 프로젝트 환경을 다른 서버로 옮길 때

다음 순서로 구성합니다.

```text
1. Python 설치
2. Python Virtualenv 생성
3. requirements.txt 설치
4. Java/Parser Runtime 준비
5. PostgreSQL 설치/실행
6. pgvector 활성화
7. Alembic Migration
8. GPU/CUDA 검증
9. BGE-M3 Model 확인
10. llama.cpp 설치
11. 사용할 LLM GGUF Model 준비
12. llama-server Model Alias 설정
13. .env 작성
14. Backend 실행
15. Frontend npm install
16. Frontend 실행
17. Smoke Test
```

LLM Model은 특정 Qwen Model을 필수로 요구하지 않습니다.

현재 Generation 인터페이스와 호환되는 llama.cpp GGUF Model을 선택하고,
`--alias`와 `LLAMA_MODEL` 값을 일치시킵니다.

---

# 68. 다른 개발자에게 Environment를 넘길 때

반드시 제공:

```text
README.md
docs/ENVIRONMENT.md
.env.example
requirements.txt
frontend/user/package.json
infra/
```

제공하지 말아야 할 것:

```text
실제 .env Secret
SSH Private Key
DB Password
JWT Secret
```

---

# 69. AI에게 Environment 문제를 맡길 때

다음 정보를 제공하면 됩니다.

```text
OS
Python Version
Virtualenv Path
GPU
CUDA
PyTorch Version
Backend Port
Frontend Port
llama.cpp Port
오류 로그
관련 .env 변수명
```

Secret 값은 마스킹합니다.

예:

```text
DATABASE_PASSWORD=***
ADMIN_JWT_SECRET=***
```

---

# 70. Environment Source of Truth

| 영역 | Source of Truth |
|---|---|
| Python Dependencies | `requirements.txt` |
| Backend Settings | `backend/app/core/config.py` |
| Runtime Environment | `.env` |
| Environment Template | `.env.example` |
| DB Session | `backend/app/db/session.py` |
| PostgreSQL Infra | `infra/docker-compose.yml` |
| pgvector Setup | `infra/postgres/init/01-enable-vector.sql` |
| Embedding Model Loader | `pipeline/embedding/model_loader.py` |
| Query Embedding | `rag/retrieval/query_embedding.py` |
| RAG Environment | `rag/service.py`, `rag/db_pipeline.py` |
| Generation Config | `rag/generation/config.py` |
| Generation Client | `rag/generation/llm_client.py` |
| User Frontend | `frontend/user/package.json` |
| Vite Proxy | `frontend/user/vite.config.ts` |
| Admin Proxy | `frontend/admin/serve_admin.py` |

---

# 71. 핵심 요약

현재 DDOKBOT 개발 환경의 핵심 구조:

```text
Project
/home/ubuntu/ddokbot/one-cycle

Python
/home/ubuntu/ddokbot/venvs/one-cycle-backend

User Frontend
Vite :5173

Backend
FastAPI :8000

Generation
llama.cpp :8080

Current LLM Test Model
Gemma GGUF

Embedding
BAAI/bge-m3

GPU
NVIDIA L4 / CUDA

Database
PostgreSQL + pgvector
```

Runtime 흐름:

```text
Browser
 ↓
Vite
 ↓
FastAPI
 ↓
PostgreSQL + pgvector
 ↓
RAG
 ↓
llama.cpp
 ↓
현재 선택된 GGUF LLM
```

Generation Model은 Source Code에 특정 Model 이름을 고정하지 않습니다.

```text
GGUF Model
   ↓
llama-server --alias
   ↓
LLAMA_MODEL
   ↓
rag/generation/config.py
   ↓
rag/generation/llm_client.py
```

구조로 연결됩니다.

따라서 향후 Gemma, Qwen 또는 다른 llama.cpp 호환 GGUF Model을 성능 비교할 때 Generation Source Code를 반복 수정하지 않고,
Model 파일, llama-server Alias, Runtime 환경변수를 변경하여 테스트합니다.

환경 문제를 수정할 때는 코드 문제와 환경 문제를 먼저 구분합니다.

```text
Connection Refused
→ Process/Port

Authentication Failed
→ Credential/DB

CUDA unavailable
→ GPU Runtime

ModuleNotFoundError
→ Virtualenv/PYTHONPATH

Evidence 정상 + Generation 실패
→ llama.cpp / Generation

curl 정상 + Browser 실패
→ Frontend Proxy / SSH Tunnel
```

환경이 정상인지 확인한 후에 실제 Application Logic을 수정합니다.

# DDOKBOT Environment

> 이 문서는 `main` 브랜치의 현재 코드와 Docker Compose 구성을 기준으로 DDOKBOT의 환경변수 구조를 설명한다.
>
> 실제 비밀번호, JWT Secret, 인증서 Private Key, AWS 내부 경로 등의 실제 운영 값은 문서에 기록하지 않는다.
> 운영 값은 프로젝트 루트의 `.env`에만 두고, 저장소에는 `.env.example`만 관리한다.

---

## 1. 기준 파일

환경변수와 실행 구성을 확인할 때 다음 파일을 기준으로 한다.

```text
.env
.env.example
infra/docker-compose.yml
backend/app/core/config.py
backend/app/services/admin_auth_service.py
backend/app/services/pipeline_gateway.py
backend/app/services/integration_service.py
backend/app/db/session.py
services/rag/config.py
rag/db/session.py
```

역할:

```text
.env
└─ 실제 실행 환경 값
   └─ Git에 커밋하지 않음

.env.example
└─ 필요한 환경변수 이름과 안전한 예시값

infra/docker-compose.yml
└─ Docker 서비스별 환경변수 주입
└─ Host 경로 Mount
└─ 컨테이너 내부 서비스 주소 설정
└─ 일부 환경변수의 Docker 기본값 제공

backend/app/core/config.py
└─ Backend 공통 환경설정

services/rag/config.py
└─ RAG Service 환경설정
```

---

## 2. 환경변수 적용 우선순위

Docker 실행에서는 `.env`에 값이 있어도 `docker-compose.yml`의 `environment:`에서 같은 변수를 다시 지정하면 Compose 값이 컨테이너 내부에서 사용된다.

Backend Docker 내부 설정:

```text
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
RAG_SERVICE_BASE_URL=http://rag:18002
DOCUMENT_WORKER_BASE_URL=http://document-worker:18003
CRAWLER_SERVICE_BASE_URL=http://crawler:8000
```

RAG Docker 내부 설정:

```text
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
EMBEDDING_SERVICE_URL=http://embedding:18001
LLAMA_BASE_URL=http://llm:8080
```

따라서 현재 운영용 `.env`에는 Docker Compose가 고정적으로 덮어쓰는 내부 서비스 주소를 중복해서 두지 않는다.

---

## 3. 현재 `.env` 구성

현재 정리된 `.env` / `.env.example`은 다음 19개 환경변수를 관리한다.

```text
ADMIN_ID
ADMIN_JWT_SECRET
ADMIN_PASSWORD

ANNOUNCEMENT_RECOLLECTOR
COLLECTION_RETENTION_MODE
COLLECTION_RUNNER

DOCUMENT_STORAGE_HOST_PATH
PIPELINE_OUTPUT_HOST_PATH

EMBEDDING_MODEL_HOST_PATH

LLAMA_MODEL
LLAMA_TIMEOUT_SECONDS
LLM_MODEL_FILE
LLM_MODEL_HOST_PATH

NGINX_TLS_CERT_PATH
NGINX_TLS_KEY_PATH

POSTGRES_DB
POSTGRES_PASSWORD
POSTGRES_PORT
POSTGRES_USER
```

---

## 4. PostgreSQL

| 환경변수 | 역할 | 사용 위치 |
|---|---|---|
| `POSTGRES_DB` | PostgreSQL Database 이름 | Backend / RAG / PostgreSQL Container |
| `POSTGRES_PORT` | Host에 노출할 PostgreSQL Port | `infra/docker-compose.yml` |
| `POSTGRES_USER` | PostgreSQL 사용자 | Backend / RAG / PostgreSQL Container |
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 | Backend / RAG / PostgreSQL Container |

Backend는 `backend/app/core/config.py`에서 PostgreSQL 설정을 읽고 `backend/app/db/session.py`에서 SQLAlchemy 연결 URL을 구성한다.

RAG Service는 `services/rag/config.py`에서 같은 DB 설정을 읽고 `rag/db/session.py`에서 PostgreSQL 연결을 구성한다.

Docker 실행 시 내부 Host와 Port는 Compose가 다음과 같이 지정한다.

```text
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

따라서 현재 `.env`에는 `POSTGRES_HOST`를 별도로 관리하지 않는다.

`.env.example` 예시:

```env
POSTGRES_DB=one_cycle
POSTGRES_PORT=5432
POSTGRES_USER=one_cycle
POSTGRES_PASSWORD=CHANGE_ME
```

---

## 5. Admin Authentication

현재 관리자 인증은 환경변수 기반으로 동작한다.

| 환경변수 | 역할 | 사용 위치 |
|---|---|---|
| `ADMIN_ID` | 관리자 로그인 ID | `backend/app/services/admin_auth_service.py` |
| `ADMIN_PASSWORD` | 관리자 로그인 Password | `backend/app/services/admin_auth_service.py` |
| `ADMIN_JWT_SECRET` | 관리자 JWT 서명 Secret | `backend/app/services/admin_auth_service.py` |

`ADMIN_ID`, `ADMIN_PASSWORD`, `ADMIN_JWT_SECRET`은 비어 있으면 인증 설정 오류가 발생할 수 있으므로 운영 `.env`에 유지한다.

`.env.example` 예시:

```env
ADMIN_ID=admin
ADMIN_PASSWORD=CHANGE_ME
ADMIN_JWT_SECRET=CHANGE_ME
```

다음 값들은 Backend 코드 기본값을 사용하므로 현재 `.env`에서는 관리하지 않는다.

```text
ADMIN_JWT_EXPIRE_SECONDS=3600
ADMIN_COOKIE_NAME=admin_access_token
ADMIN_COOKIE_SECURE=false
ADMIN_COOKIE_SAMESITE=lax
```

---

## 6. Collection / Recollection

전체 수집과 개별 공고 재수집은 Backend Pipeline Gateway가 환경변수에 지정된 Python callable을 동적으로 로드한다.

| 환경변수 | 역할 | 사용 위치 |
|---|---|---|
| `COLLECTION_RUNNER` | 전체 공고 수집 진입 callable | `backend/app/services/pipeline_gateway.py` |
| `ANNOUNCEMENT_RECOLLECTOR` | 개별 공고 재수집 진입 callable | `backend/app/services/pipeline_gateway.py` |
| `COLLECTION_RETENTION_MODE` | Publish 이후 Collection 정리 정책 | `backend/app/services/integration_service.py` |

현재 callable:

```env
COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
ANNOUNCEMENT_RECOLLECTOR=backend.app.services.integration_service:recollect_persist_and_process
```

연결 구조:

```text
Backend
  ↓
pipeline_gateway.py
  ↓
COLLECTION_RUNNER / ANNOUNCEMENT_RECOLLECTOR
  ↓
integration_service.py
  ├─ collect_persist_and_process()
  └─ recollect_persist_and_process()
```

### `COLLECTION_RETENTION_MODE`

지원 값:

```text
disabled
dry_run
delete
```

| 값 | 동작 |
|---|---|
| `disabled` | Collection 정리 수행 안 함 |
| `dry_run` | 실제 삭제 없이 정리 대상 계산 |
| `delete` | Publish 이후 Retention 정리 수행 |

현재 AWS 운영 `.env`는 `delete`를 사용한다.

```env
COLLECTION_RETENTION_MODE=delete
```

`.env.example`은 안전한 기본 예시로 다음 값을 권장한다.

```env
COLLECTION_RETENTION_MODE=disabled
```

---

## 7. Document / Pipeline Storage

문서 파일과 Pipeline 산출물은 Host 디렉터리를 Docker Container에 Bind Mount하여 공유한다.

| 환경변수 | 역할 | Container Mount |
|---|---|---|
| `DOCUMENT_STORAGE_HOST_PATH` | Host 문서 저장 디렉터리 | `/data/documents` |
| `PIPELINE_OUTPUT_HOST_PATH` | Host Pipeline 결과 디렉터리 | `/app/outputs` |

`DOCUMENT_STORAGE_HOST_PATH` 사용 서비스:

```text
crawler
backend
scheduler
document-worker
```

`PIPELINE_OUTPUT_HOST_PATH` 사용 서비스:

```text
backend
scheduler
document-worker
```

Compose 기본값:

```text
DOCUMENT_STORAGE_HOST_PATH
→ ../runtime/documents

PIPELINE_OUTPUT_HOST_PATH
→ ../runtime/outputs
```

운영 AWS에서는 실제 Host 디렉터리를 명확하게 지정하기 위해 `.env`에서 관리한다.

`.env.example`:

```env
DOCUMENT_STORAGE_HOST_PATH=/path/to/runtime/documents
PIPELINE_OUTPUT_HOST_PATH=/path/to/runtime/outputs
```

---

## 8. Embedding Model Storage

현재 `.env`에서는 Embedding Runtime 세부 옵션이 아니라 Host의 Embedding Model 위치만 관리한다.

```text
EMBEDDING_MODEL_HOST_PATH
```

Docker Mount:

```text
Host EMBEDDING_MODEL_HOST_PATH
        ↓
Container /models/bge-m3
```

Compose 내부 설정:

```text
EMBEDDING_MODEL_NAME
기본값 → BAAI/bge-m3

EMBEDDING_MODEL_PATH
→ /models/bge-m3

EMBEDDING_USE_FP16
기본값 → true

EMBEDDING_REQUIRE_CUDA
기본값 → true

EMBEDDING_DEVICE_INDEX
기본값 → 0
```

현재 운영 `.env`에서는 위 Runtime 기본값을 중복 관리하지 않고 모델 Host 경로만 유지한다.

```env
EMBEDDING_MODEL_HOST_PATH=/path/to/models/embedding/bge-m3
```

---

## 9. RAG / LLM

| 환경변수 | 역할 | 사용 위치 |
|---|---|---|
| `LLAMA_MODEL` | RAG Service에서 사용하는 Model 이름 | `services/rag/config.py`, `infra/docker-compose.yml` |
| `LLAMA_TIMEOUT_SECONDS` | RAG Service의 llama.cpp 요청 Timeout | `services/rag/config.py` |
| `LLM_MODEL_FILE` | llama.cpp Container가 로드할 GGUF 파일명 | `infra/docker-compose.yml` |
| `LLM_MODEL_HOST_PATH` | Host의 LLM Model 디렉터리 | `infra/docker-compose.yml` |

### `LLAMA_MODEL`

Compose:

```text
LLAMA_MODEL=${LLAMA_MODEL:-gemma}
```

`.env.example`:

```env
LLAMA_MODEL=gemma
```

### `LLAMA_TIMEOUT_SECONDS`

`services/rag/config.py`의 코드 기본값은 `180`초다.

현재 AWS 운영에서는 다음 값으로 오버라이드한다.

```env
LLAMA_TIMEOUT_SECONDS=600
```

### `LLM_MODEL_FILE`

Compose:

```text
LLM_MODEL_PATH=/models/${LLM_MODEL_FILE:-gemma-4-12B-it-Q4_0.gguf}
```

`.env.example`:

```env
LLM_MODEL_FILE=gemma-4-12B-it-Q4_0.gguf
```

### `LLM_MODEL_HOST_PATH`

Host 모델 디렉터리를 Container의 `/models`에 Read-only Mount한다.

```text
Host LLM_MODEL_HOST_PATH
      ↓
Container /models
```

Compose 기본값:

```text
../models/llm
```

`.env.example`:

```env
LLM_MODEL_HOST_PATH=/path/to/models/llm
```

### 내부 서비스 주소

RAG Container는 llama.cpp를 다음 Docker 내부 주소로 호출한다.

```text
http://llm:8080
```

Embedding Service는 다음 주소를 사용한다.

```text
http://embedding:18001
```

두 주소는 `docker-compose.yml`에서 지정되므로 현재 운영 `.env`에는 `LLAMA_BASE_URL`, `EMBEDDING_SERVICE_URL`을 두지 않는다.

---

## 10. Nginx / TLS

| 환경변수 | 역할 | Container Target |
|---|---|---|
| `NGINX_TLS_CERT_PATH` | TLS 인증서 Host 경로 | `/etc/nginx/certs/origin.pem` |
| `NGINX_TLS_KEY_PATH` | TLS Private Key Host 경로 | `/etc/nginx/certs/origin.key` |

Compose 기본값:

```text
NGINX_TLS_CERT_PATH
→ ./nginx/certs/origin.pem

NGINX_TLS_KEY_PATH
→ ./nginx/certs/origin.key
```

운영 AWS에서는 실제 Host 경로를 `.env`에서 지정한다.

`.env.example`:

```env
NGINX_TLS_CERT_PATH=/path/to/nginx/certs/origin.pem
NGINX_TLS_KEY_PATH=/path/to/nginx/certs/origin.key
```

---

## 11. 현재 `.env.example` 권장 형태

```env
# ============================================================
# PostgreSQL
# ============================================================

POSTGRES_DB=one_cycle
POSTGRES_PORT=5432
POSTGRES_USER=one_cycle
POSTGRES_PASSWORD=CHANGE_ME


# ============================================================
# Admin Authentication
# ============================================================

ADMIN_ID=admin
ADMIN_PASSWORD=CHANGE_ME
ADMIN_JWT_SECRET=CHANGE_ME


# ============================================================
# Collection / Recollection
# ============================================================

COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
ANNOUNCEMENT_RECOLLECTOR=backend.app.services.integration_service:recollect_persist_and_process

# disabled | dry_run | delete
COLLECTION_RETENTION_MODE=disabled


# ============================================================
# Document / Pipeline Storage
# ============================================================

DOCUMENT_STORAGE_HOST_PATH=/path/to/runtime/documents
PIPELINE_OUTPUT_HOST_PATH=/path/to/runtime/outputs


# ============================================================
# Embedding
# ============================================================

EMBEDDING_MODEL_HOST_PATH=/path/to/models/embedding/bge-m3


# ============================================================
# RAG / LLM
# ============================================================

LLAMA_MODEL=gemma
LLAMA_TIMEOUT_SECONDS=600

LLM_MODEL_FILE=gemma-4-12B-it-Q4_0.gguf
LLM_MODEL_HOST_PATH=/path/to/models/llm


# ============================================================
# Nginx / TLS
# ============================================================

NGINX_TLS_CERT_PATH=/path/to/nginx/certs/origin.pem
NGINX_TLS_KEY_PATH=/path/to/nginx/certs/origin.key
```

---

## 12. `.env`와 `.env.example` 관리 원칙

두 파일은 Key 구조를 동일하게 유지한다.

```text
.env.example
→ 저장소에 커밋 가능
→ Secret은 CHANGE_ME
→ 실제 AWS 절대경로 대신 /path/to/... 사용

.env
→ 실제 운영값
→ Git에 커밋하지 않음
→ 실제 Password / Secret / Host 경로 사용
```

---

## 13. Key 일치 여부 확인

`.env` Key:

```bash
grep -v '^[[:space:]]*#' .env   | grep -v '^[[:space:]]*$'   | sed 's/[[:space:]]*=.*//'   | sort
```

`.env.example` Key:

```bash
grep -v '^[[:space:]]*#' .env.example   | grep -v '^[[:space:]]*$'   | sed 's/[[:space:]]*=.*//'   | sort
```

`.env`에만 있는 Key:

```bash
comm -23   <(grep -v '^[[:space:]]*#' .env | grep -v '^[[:space:]]*$' | sed 's/[[:space:]]*=.*//' | sort)   <(grep -v '^[[:space:]]*#' .env.example | grep -v '^[[:space:]]*$' | sed 's/[[:space:]]*=.*//' | sort)
```

`.env.example`에만 있는 Key:

```bash
comm -13   <(grep -v '^[[:space:]]*#' .env | grep -v '^[[:space:]]*$' | sed 's/[[:space:]]*=.*//' | sort)   <(grep -v '^[[:space:]]*#' .env.example | grep -v '^[[:space:]]*$' | sed 's/[[:space:]]*=.*//' | sort)
```

두 명령 모두 출력이 없으면 Key 구성이 동일하다.

---

## 14. 현재 제거한 Legacy / 중복 환경변수

현재 운영 `.env`에서는 아래 항목을 제거했다.

```text
CRAWLER_MAX_NOTICES
CRAWLER_STORAGE_ROOT
DOCUMENT_REPROCESSOR

RAG_ANSWER_FUNCTION
RAG_DB_TOP_K
RAG_RUNTIME
MVP_ANNOUNCEMENT_ID

POSTGRES_HOST
RAG_SERVICE_BASE_URL
EMBEDDING_SERVICE_URL
LLAMA_BASE_URL

EMBEDDING_MODEL_NAME
EMBEDDING_MODEL_PATH
EMBEDDING_DEVICE_INDEX
EMBEDDING_REQUIRE_CUDA
EMBEDDING_USE_FP16

ADMIN_JWT_EXPIRE_SECONDS
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SECURE
ADMIN_COOKIE_SAMESITE
```

여기에는 두 종류가 섞여 있다.

```text
1. 현재 Runtime에서 사용하지 않는 Legacy 변수
2. 코드 또는 Docker Compose 기본값으로 충분하여 .env에서만 제거한 변수
```

따라서 위 목록을 모두 "코드에서 존재하지 않는 변수"로 해석하면 안 된다.

향후 Local Native 실행으로 구조가 바뀌거나 기본값과 다른 Runtime 설정이 필요해지면 코드와 Compose를 다시 확인해 재도입 여부를 판단한다.

---

## 15. 변경 시 확인 순서

```text
1. 실제 코드에서 환경변수 참조 여부 확인
        ↓
2. config.py 기본값 확인
        ↓
3. infra/docker-compose.yml의 environment / interpolation 확인
        ↓
4. .env에서 실제 Override가 필요한지 판단
        ↓
5. .env.example Key 구조 동기화
        ↓
6. 관련 Service 재시작 및 동작 확인
```

파일이 존재한다는 이유만으로 실제 Runtime에서 사용한다고 판단하지 않는다.

---

## 16. 보안 원칙

실제 값을 외부에 노출하지 않는 항목:

```text
POSTGRES_PASSWORD
ADMIN_PASSWORD
ADMIN_JWT_SECRET
TLS Private Key
SSH Private Key
```

`.env`는 Git에 커밋하지 않는다.

환경변수 목록을 확인할 때도 가능하면 실제 값이 아닌 Key 이름만 출력한다.

---

## 17. 요약

현재 DDOKBOT 운영 환경변수는 19개 Key를 관리한다.

```text
PostgreSQL
├─ POSTGRES_DB
├─ POSTGRES_PORT
├─ POSTGRES_USER
└─ POSTGRES_PASSWORD

Admin
├─ ADMIN_ID
├─ ADMIN_PASSWORD
└─ ADMIN_JWT_SECRET

Collection
├─ COLLECTION_RUNNER
├─ ANNOUNCEMENT_RECOLLECTOR
└─ COLLECTION_RETENTION_MODE

Storage
├─ DOCUMENT_STORAGE_HOST_PATH
└─ PIPELINE_OUTPUT_HOST_PATH

Embedding
└─ EMBEDDING_MODEL_HOST_PATH

RAG / LLM
├─ LLAMA_MODEL
├─ LLAMA_TIMEOUT_SECONDS
├─ LLM_MODEL_FILE
└─ LLM_MODEL_HOST_PATH

Nginx / TLS
├─ NGINX_TLS_CERT_PATH
└─ NGINX_TLS_KEY_PATH
```

실제 Runtime 동작은 `.env` 하나만으로 판단하지 않고 다음을 함께 확인한다.

```text
.env
+
infra/docker-compose.yml
+
각 Service config.py
+
실제 호출 코드
```

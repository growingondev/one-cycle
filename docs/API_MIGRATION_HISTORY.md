# DDOKBOT API Service Migration History

## 1. 문서 목적

이 문서는 기존 DDOKBOT MVP의 실행 구조를 보존하면서, Docker 기반 서비스 분리 및 HTTP API 통신 구조로 전환하는 과정을 기록한다.

기존 완성 버전은 `develop` 브랜치에 유지하고, API 서비스 분리 버전은 `develop-api` 브랜치에서 별도로 통합한다.

본 문서는 다음 내용을 지속적으로 기록한다.

- API 서비스 분리를 시작한 이유
- 브랜치 운영 기준
- 단계별 변경 범위
- 서비스 간 통신 계약
- 테스트 및 검증 결과
- 기존 버전과의 차이
- 다음 단계 작업
- 문제 발생 시 복구 기준

---

## 2. API 전환 배경

기존 MVP는 동일한 Python 실행 환경 안에서 모듈 import와 함수 직접 호출 방식으로 구성되어 있다.

~~~text
Backend
├─ Python direct call → RAG
└─ Python direct call → Document Processing Pipeline
~~~

이 구조는 MVP 기능 검증에는 적합하지만, 각 기능을 Docker Container 단위의 독립 Service로 분리하면 다른 Container의 Python 함수를 직접 import하여 호출할 수 없다.

따라서 API 버전에서는 다음 원칙을 적용한다.

> 같은 Service Container 내부의 코드는 기존 Python 호출 방식을 유지할 수 있다.
> 서로 다른 Service Container 사이의 통신만 HTTP API로 변경한다.

목표 구조는 다음과 같다.

~~~text
Frontend
   ↓ HTTP
Backend
   ├─ HTTP → RAG Service
   ├─ HTTP → Document Worker
   └─ PostgreSQL

Document Worker
   ├─ Parser
   ├─ Normalizer
   ├─ Structure / Verification
   ├─ Chunking
   ├─ HTTP → Embedding Service
   └─ Key Information Extraction

RAG Service
   ├─ HTTP → Embedding Service
   ├─ PostgreSQL Retrieval
   └─ HTTP → llama.cpp
~~~

---

## 3. 브랜치 운영 기준

API 서비스 분리 작업은 기존 `develop`에 바로 병합하지 않는다.

~~~text
develop
└─ 기존 MVP 완성 버전 보존

develop-api
└─ API / Docker 서비스 분리 버전 통합

feature/backend-api-integration
└─ Backend 내부 Service HTTP 연동 작업
~~~

API 관련 Feature Branch의 PR Base는 원칙적으로 `develop-api`를 사용한다.

API 버전의 Docker 통합 및 E2E 검증이 완료되기 전까지 `develop-api`를 기존 `develop`에 병합하지 않는다.

이를 통해 API 전환 과정에 문제가 발생하더라도 기존 MVP 완성 버전을 계속 사용할 수 있도록 한다.

---

# Phase 1. Backend Internal HTTP Client Layer

## 4. 작업 상태

**완료**

작업 브랜치:

~~~text
feature/backend-api-integration
~~~

작업 기준 Commit:

~~~text
296ba3a
Merge pull request #60 from growingondev/feature/rag
~~~

---

## 5. Phase 1 목적

기존 Backend의 실제 호출 방식을 즉시 제거하지 않고, 향후 RAG Service와 Document Worker를 HTTP로 호출하기 위한 Client Layer를 먼저 준비한다.

따라서 Phase 1에서는 기존 Runtime 호출 흐름을 변경하지 않는다.

현재 구조:

~~~text
Backend
├─ 기존 Python direct call       ← 유지
└─ Internal HTTP Client Layer    ← 신규 추가
   ├─ RAG Client
   └─ Document Worker Client
~~~

---

## 6. 변경 파일

### 신규 파일

~~~text
backend/app/clients/__init__.py
backend/app/clients/http_json.py
backend/app/clients/rag_client.py
backend/app/clients/document_worker_client.py

tests/backend/test_internal_http_client.py
tests/backend/test_rag_client.py
tests/backend/test_document_worker_client.py
~~~

### 수정 파일

~~~text
backend/app/core/config.py
.env.example
~~~

---

## 7. 공통 HTTP Client

파일:

~~~text
backend/app/clients/http_json.py
~~~

### 역할

- 내부 Service JSON POST 요청
- HTTP/HTTPS URL 검증
- Timeout 검증
- JSON 직렬화
- 연결 실패 처리
- Timeout 처리
- HTTP 4xx/5xx 처리
- Service Error Contract 전달
- 잘못된 JSON Response 차단

### Exception 구조

~~~text
InternalServiceClientError
├─ InternalServiceConfigurationError
├─ InternalServiceUnavailableError
├─ InternalServiceResponseError
└─ InternalServiceHTTPError
~~~

내부 Service가 다음과 같은 오류를 반환하면:

~~~json
{
  "error": {
    "code": "RAG_EMBEDDING_UNAVAILABLE",
    "message": "Embedding service unavailable."
  }
}
~~~

Backend Client는 다음 정보를 유지한다.

- HTTP status code
- Service error code
- Service error message

---

## 8. RAG Client

파일:

~~~text
backend/app/clients/rag_client.py
~~~

예정 Endpoint:

~~~text
POST /v1/rag/answer
~~~

Request:

~~~json
{
  "announcement_id": 1,
  "question": "신청 기간은 언제인가요?"
}
~~~

RAG Service의 Business Result는 다음 세 종류를 허용한다.

~~~text
grounded
no_evidence
unsupported
~~~

Response 기본 구조:

~~~json
{
  "result": "grounded",
  "answer": "...",
  "grounded": true,
  "evidence": [
    {
      "chunk_id": "chunk-001",
      "section_title": "...",
      "content": "...",
      "score": 0.84
    }
  ]
}
~~~

Backend 외부 Chat API와 RAG 내부 Service API의 계약은 분리한다.

외부 Frontend 계약은 기존 camelCase 형식을 유지하고, 내부 Service 통신은 snake_case를 사용한다.

실제 HTTP 전환 단계에서는 Backend Service Layer가 두 계약 사이의 Adapter 역할을 담당한다.

---

## 9. Document Worker Client

파일:

~~~text
backend/app/clients/document_worker_client.py
~~~

예정 Endpoint:

~~~text
POST /v1/documents/{document_id}/process
~~~

Request:

~~~json
{
  "announcement_id": 1,
  "announcement_key": "announcement_001",
  "source": {
    "filename": "announcement.hwpx",
    "format": "hwpx",
    "storage_path": "/data/documents/announcement.hwpx"
  }
}
~~~

Backend는 기존 DB를 통해 Worker 호출에 필요한 다음 Context를 구성할 수 있다.

~~~text
announcement_key
announcement_id
document_id
filename
format
storage_path
~~~

### Key Information 계약

Worker 성공 Response에는 다음 7개 필드가 모두 존재해야 한다.

~~~text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
~~~

다음 상태는 정상 결과다.

~~~json
{
  "status": "not_found"
}
~~~

`not_found`는 추출기가 정상 실행됐지만 원문에서 해당 정보를 찾지 못했다는 의미이며 Worker 전체 실패로 처리하지 않는다.

반면 다음 경우는 정상 성공 Response로 인정하지 않는다.

- 필수 7개 필드 중 하나 이상 누락
- Key Information 필드 타입 오류
- Worker Response Schema 불일치

---

## 10. Service 환경설정

Phase 1에서 다음 설정을 추가했다.

~~~text
RAG_SERVICE_BASE_URL
RAG_SERVICE_TIMEOUT_SECONDS

DOCUMENT_WORKER_BASE_URL
DOCUMENT_WORKER_TIMEOUT_SECONDS
~~~

현재 Base URL은 비워 둔다.

실제 Service hostname과 port는 Docker Compose 통합 단계에서 확정한다.

현재 Timeout 기본값:

| Service | Timeout |
| --- | ---: |
| RAG | 60초 |
| Document Worker | 600초 |

이 값은 초기 운영을 위한 기본값이며 실제 처리시간 측정 후 조정할 수 있다.

---

## 11. Phase 1 테스트 결과

신규 Client Test 결과:

~~~text
Ran 13 tests
OK
~~~

검증 항목:

- 정상 JSON POST
- HTTP 오류 계약 보존
- 연결 실패 처리
- 잘못된 JSON Response 차단
- RAG Request 생성
- `grounded` Response
- `no_evidence` Response
- `unsupported` Response
- RAG Schema 오류 차단
- Worker Request 생성
- Key Information 7개 필드 검증
- `not_found` 정상 허용
- Key Information 누락 및 타입 오류 차단

추가 검증:

~~~text
python -m compileall backend/app/clients
PASS

git diff --check
PASS
~~~

---

## 12. 전체 Backend 회귀 테스트 참고

Phase 1 작업 후 Backend 전체 테스트 결과:

~~~text
Ran 88 tests
FAILED (failures=4)
~~~

실패한 테스트:

~~~text
test_application_period
test_application_period_korean_ampm_range
test_application_period_labeled_range
test_supply_summary_is_compact
~~~

4개 실패는 모두 기존 `KeyInformationExtractor` 영역이다.

Phase 1에서는 다음 파일을 수정하지 않았다.

~~~text
pipeline/key_information_extractor.py
tests/backend/test_key_information_extractor.py
~~~

따라서 해당 실패는 Backend API Client Layer 변경과 분리하여 관리한다.

이번 Backend API 전환 작업에서 Document Processing 내부 로직을 임의로 수정하지 않는다.

---

## 13. Phase 1에서 변경하지 않은 Runtime

다음 기존 호출 방식은 아직 유지한다.

### Backend → RAG

~~~text
RAG_ANSWER_FUNCTION
→ Python callable
~~~

### Backend → Document Processing

~~~text
DOCUMENT_REPROCESSOR
→ Python callable
~~~

아직 수정하지 않는 주요 파일:

~~~text
backend/app/services/chat_service.py
backend/app/services/pipeline_gateway.py
pipeline/document_processor.py
~~~

RAG와 Document Worker의 실제 HTTP Server Endpoint가 준비되기 전에 Client 호출로 교체하면 현재 Runtime이 동작하지 않기 때문에 의도적으로 유지한다.

---

# 향후 작업

## 14. Phase 2 - Service Endpoint 준비

필요 Endpoint:

~~~text
RAG
POST /v1/rag/answer

Document Worker
POST /v1/documents/{document_id}/process

Embedding
POST /v1/embeddings
~~~

각 Service에서 실제 HTTP Server Endpoint를 구현한다.

---

## 15. Phase 3 - Backend 실제 호출 전환

RAG Endpoint 준비 후:

~~~text
chat_service

Python direct call
        ↓
RAG HTTP Client
~~~

Document Worker Endpoint 준비 후:

~~~text
pipeline_gateway

Python direct call
        ↓
Document Worker HTTP Client
~~~

---

## 16. Phase 4 - Cross-Service 의존 제거

Container 경계를 넘는 Python import를 제거한다.

주요 목표:

- RAG의 Backend DB Session 직접 import 제거
- Worker의 Backend Service 직접 import 제거
- Worker → Embedding을 HTTP API로 전환
- RAG → Embedding을 HTTP API로 전환

---

## 17. Phase 5 - Docker Compose 통합

예상 Service:

~~~text
nginx
backend
document-worker
rag
embedding
llm
postgres
~~~

Docker 내부 Service 통신에서는 `localhost`가 아니라 Docker Compose의 Service Name을 hostname으로 사용한다.

---

## 18. Phase 6 - E2E 검증

최종적으로 다음 전체 흐름을 검증한다.

~~~text
Frontend
    ↓
Backend
    ↓
Document Worker / RAG
    ↓
Embedding / LLM / PostgreSQL
    ↓
Backend
    ↓
Frontend
~~~

---

## 19. 현재 Checkpoint

Phase 1 완료 시점에서 기존 `develop` 브랜치는 변경하지 않았다.

API 전환 작업은 다음 계열에서만 진행한다.

~~~text
develop-api
└─ feature/backend-api-integration
~~~

따라서 API 전환 과정에서 문제가 발생하더라도 기존 MVP 완성 버전은 `develop`에서 계속 보존된다.

---

## 20. 2026-08-28 Internal Service API 계약 확정

Phase 1의 Backend HTTP Client Layer를 `develop-api`에 병합한 뒤, Document Processing 및 RAG/Embedding 담당자와 실제 Client 계약을 기준으로 서비스 간 API 계약을 확인했다.

상세 계약은 다음 문서에서 관리한다.

~~~text
docs/SERVICE_API_CONTRACT.md
~~~

### 계약 확정 상태

~~~text
Document Worker Contract   CONFIRMED
RAG Contract               CONFIRMED
Embedding Contract         CONFIRMED
Shared Volume Direction    CONFIRMED
~~~

### Document Worker

확정 Endpoint:

~~~text
POST /v1/documents/{document_id}/process
~~~

Backend는 다음 Context를 전달한다.

~~~text
document_id
announcement_id
announcement_key
filename
format
storage_path
~~~

Document Worker의 책임 범위는 다음과 같이 확정했다.

~~~text
Parser
→ Normalizer
→ Structure / Verification
→ Chunking
→ Embedding Service 호출
→ Key Information Extraction
→ Artifact 생성
→ 결과 반환
~~~

Worker는 DB Persistence, Key Information DB 저장, ProcessingRun 상태 처리를 직접 수행하지 않는다.

Artifact 파일 자체를 HTTP Response에 포함하지 않고 shared output 경로에 생성한다.

Worker 성공 Response는 현재 Backend Client 계약대로 다음 정보를 반환한다.

~~~text
output_path
summary
key_information
~~~

Backend는 `output_path`를 기준으로 Artifact를 검증한 후 DB Persistence 및 ProcessingRun 처리를 담당한다.

Key Information 7개 필드는 모두 필수이며 개별 필드의 다음 상태는 정상 결과로 인정한다.

~~~json
{
  "status": "not_found"
}
~~~

Worker는 우선 동기 HTTP 방식으로 구현하며 Backend의 초기 timeout은 600초를 사용한다.

실제 Docker 환경의 처리시간 측정 후 필요한 경우에만 `202 Accepted + job_id` 기반 비동기 방식 전환을 검토한다.

### RAG

확정 Endpoint:

~~~text
POST /v1/rag/answer
~~~

Request:

~~~json
{
  "announcement_id": 1,
  "question": "신청 기간은 언제인가요?"
}
~~~

RAG는 전달받은 공고 범위에서 Retrieval을 수행하고 `answer + evidence`를 반환한다.

Business Result는 기존 Backend Client 계약대로 다음 세 상태를 유지한다.

~~~text
grounded
no_evidence
unsupported
~~~

### Embedding

확정 Endpoint:

~~~text
POST /v1/embeddings
~~~

Document Worker의 Chunk Embedding과 RAG의 Query Embedding이 동일 Endpoint를 사용한다.

Request:

~~~json
{
  "items": [
    {
      "id": "chunk-001",
      "text": "..."
    }
  ]
}
~~~

Response:

~~~json
{
  "model": "BAAI/bge-m3",
  "dimension": 1024,
  "normalized": true,
  "items": [
    {
      "id": "chunk-001",
      "embedding": [...]
    }
  ]
}
~~~

추가 계약 규칙:

- `items`는 1개 이상
- `items[].id`는 Request 내 중복 불가
- `items[].text`는 빈 문자열 불가
- Response 배열 순서에 의존하지 않음
- Request와 Response는 `id` 기준으로 매칭
- 성공 Response에는 요청한 모든 `id`가 정확히 1개씩 존재
- Request에 없는 추가 `id`는 반환하지 않음
- 오류는 공통 Internal Service Error Contract 사용

RAG Query는 동일 Endpoint에 다음과 같이 1건을 전달한다.

~~~json
{
  "items": [
    {
      "id": "query",
      "text": "..."
    }
  ]
}
~~~

### Shared Volume

Backend와 Document Worker는 Docker Compose에서 다음 경로를 동일한 Container 내부 경로로 공유한다.

~~~text
/data/documents
/data/outputs
~~~

Backend가 Worker에 전달한 `storage_path`는 Worker Container에서도 동일한 경로로 접근 가능해야 한다.

Worker가 생성하고 반환한 `output_path` 역시 Backend Container에서 동일한 경로로 접근 가능해야 한다.

실제 Docker volume 이름과 host mount 위치는 Docker Compose 통합 단계에서 확정한다.

### 현재 구현 상태

계약 확정과 Endpoint 구현 완료는 구분한다.

~~~text
Backend HTTP Client         IMPLEMENTED

Document Worker Endpoint    PENDING
RAG Endpoint                PENDING
Embedding Endpoint          PENDING

Backend Runtime Cutover     PENDING
Docker Compose Integration  PENDING
E2E                         PENDING
~~~

따라서 현재 시점에는 기존 Python direct call을 유지한다.

각 Service Endpoint가 구현된 후 `develop-api`에서 실제 HTTP Runtime 전환과 통합 검증을 진행한다.

---

## 21. 2026-08-28 Backend Document Worker Orchestration 준비

Document Worker의 실제 HTTP Endpoint 구현 전에 Backend 측 Worker 연동 및 Persistence 책임을 구현했다.

이번 단계에서는 기존 MVP Runtime의 `DOCUMENT_REPROCESSOR` 직접 호출은 변경하지 않았다.

### 구현한 Backend 처리 흐름

신규 Service:

~~~text
backend/app/services/document_processing_service.py
~~~

처리 흐름:

~~~text
DB Document Context 조회
→ Document Worker HTTP Client
→ Worker Response Contract 검증
→ output_path 기준 Artifact 검증/Persistence
→ inactive ProcessingRun 생성
→ Key Information DB 저장
→ ProcessingRun 활성화
~~~

Worker Response의 다음 식별값도 요청한 DB Context와 일치하는지 검증한다.

~~~text
document_id
announcement_id
announcement_key
document_format
~~~

### Worker 결과 Persistence

기존 `pipeline_persistence.py`를 확장하여 Worker Response의 `output_path`를 선택적으로 사용할 수 있게 했다.

기존 MVP 호출은 그대로 유지한다.

~~~text
persist_document_outputs(document_id)
~~~

API 버전에서는 다음 방식으로 Worker Artifact 경로를 전달할 수 있다.

~~~text
persist_document_outputs(
    document_id,
    output_root_path=response.output_path,
)
~~~

Worker의 `summary.chunk_count`, `summary.embedding_count`와 실제 DB Persistence 결과도 비교한다.

불일치 시 새 ProcessingRun을 활성화하지 않고 failed 상태로 기록한다.

### ProcessingRun 실패 처리

ProcessingRun 생성 이후 다음 단계에서 오류가 발생하면 새 Run을 failed 처리한다.

~~~text
persistence summary validation
key_information persistence
activation
~~~

기존 active ProcessingRun은 유지한다.

Artifact Persistence transaction 자체가 실패하여 유효한 새 `processing_run_id`가 없는 경우에는 존재하지 않는 ProcessingRun을 임의로 failed 처리하지 않는다.

### Shared Volume 경로 처리

Docker 서비스 계약은 기존대로 다음 경로를 사용한다.

~~~text
/data/documents
/data/outputs
~~~

Windows 로컬 Python에서는 `/data/...`를 `C:\data\...`로 잘못 해석할 수 있으므로 암묵적인 경로 변환을 하지 않는다.

Windows host에서는 Docker POSIX 경로 직접 접근을 명시적으로 차단하고, 실제 API 통합 시 Backend와 Worker Container가 동일 `/data/...` 경로를 사용한다.

Worker `output_path`는 다음 경로 식별값도 검증한다.

~~~text
{announcement_key}
/document_{document_id}
~~~

### 테스트

신규 테스트:

~~~text
tests/backend/test_document_processing_service.py
tests/backend/test_pipeline_persistence_paths.py
~~~

검증 결과:

~~~text
Document Worker / Persistence 관련 테스트
Ran 18 tests
OK

관련 Backend 회귀 테스트
Ran 53 tests
OK

전체 Backend 테스트
Ran 106 tests
FAILED (failures=4)
~~~

전체 테스트의 4개 실패는 이전 Phase 1부터 존재한 기존 KeyInformationExtractor 테스트와 동일하다.

~~~text
test_application_period
test_application_period_korean_ampm_range
test_application_period_labeled_range
test_supply_summary_is_compact
~~~

이번 Backend Worker Orchestration 작업으로 새롭게 발생한 회귀 실패는 확인되지 않았다.

### 현재 구현 상태

~~~text
Backend Worker HTTP Client        IMPLEMENTED
Backend Worker Orchestration      IMPLEMENTED
Worker Artifact Persistence       IMPLEMENTED

Document Worker Endpoint          PENDING
Backend Runtime Cutover           PENDING
Docker Compose Integration        PENDING
E2E                               PENDING
~~~

실제 Worker Endpoint가 준비될 때까지 Runtime은 기존 구조를 유지한다.

현재:

~~~text
DOCUMENT_REPROCESSOR
→ Python callable
~~~

향후:

~~~text
Backend
→ process_document_with_worker()
→ Document Worker HTTP
→ Backend Persistence
~~~

---

## 22. 2026-08-28 Embedding API develop-api 반영 확인

`develop-api`에 Embedding Service API 구현 PR이 병합되어 Backend API 통합 브랜치에도 최신 변경을 반영했다.

이번 변경은 Embedding Service 담당 구현을 Backend에서 새로 작성한 것이 아니라, `develop-api`에 병합된 구현을 통합 브랜치에서 받아 계약 일치 여부를 확인한 것이다.

### 반영된 Service

~~~text
services/embedding/main.py
services/embedding/schemas.py
services/embedding/service.py
~~~

구현 Endpoint:

~~~text
POST /v1/embeddings
~~~

### 기존 확정 계약과의 확인 결과

Request:

~~~json
{
  "items": [
    {
      "id": "chunk-001",
      "text": "..."
    }
  ]
}
~~~

다음 검증이 구현되어 있다.

~~~text
items >= 1
id non-empty
text non-empty
request 내부 id unique
~~~

Response:

~~~json
{
  "model": "...",
  "dimension": 1024,
  "normalized": true,
  "items": [
    {
      "id": "chunk-001",
      "embedding": []
    }
  ]
}
~~~

기존 Service API Contract에서 확정한 응답 필드와 일치한다.

오류 응답도 공통 내부 서비스 형식을 사용한다.

~~~text
422 EMBEDDING_INVALID_REQUEST
503 EMBEDDING_MODEL_UNAVAILABLE
500 EMBEDDING_GENERATION_FAILED
~~~

### 현재 구현 상태 변경

이전:

~~~text
Embedding Endpoint  PENDING
~~~

현재:

~~~text
Embedding Endpoint  IMPLEMENTED
~~~

다만 다음 단계는 아직 남아 있다.

~~~text
Document Worker → Embedding HTTP 실제 연결
RAG → Embedding HTTP 실제 연결
Docker Compose service 등록/연결
Container 환경 E2E 검증
~~~

따라서 Endpoint 구현 완료와 전체 서비스 통합 완료는 별도 상태로 관리한다.

---

## 23. 2026-08-28 Document Worker API 부분 구현 반영 확인

`develop-api`에 Document Worker API 구현 PR이 병합되어 Backend API 통합 브랜치에도 최신 변경을 반영했다.

이번 변경은 Document Worker 담당 코드를 Backend에서 새로 구현한 것이 아니라, `develop-api`에 병합된 구현을 통합 브랜치에서 받아 기존 Backend HTTP Client 계약과의 호환성을 확인한 것이다.

### 반영된 Service

~~~text
document_worker/api/routes.py
document_worker/api/schemas.py
document_worker/main.py
document_worker/service.py
~~~

구현 Endpoint:

~~~text
POST /v1/documents/{document_id}/process
~~~

### 현재 구현 범위

현재 Worker의 실제 처리 흐름은 다음 단계까지 구현되어 있다.

~~~text
원본 파일 확인
→ 실제 HWP/HWPX 형식 확인
→ Parser
→ Normalizer
→ Structure / Verification
→ Chunking
~~~

Chunking 이후 다음 단계는 아직 구현되지 않았다.

~~~text
Document Worker → Embedding HTTP
→ Embedding Artifact 생성
→ Key Information Extraction
→ completed Response 반환
~~~

현재 Worker는 Chunking 완료 후 `NotImplementedError`를 발생시키며 Endpoint에서는 이를 다음 오류로 반환한다.

~~~text
HTTP 501
DOCUMENT_PROCESSING_NOT_IMPLEMENTED
~~~

따라서 Endpoint 자체는 존재하지만 전체 Document Processing 정상 완료 경로는 아직 구현 중이다.

### Backend Client 계약 확인

Backend HTTP Client와 Worker Request Schema의 필드를 대조했다.

~~~text
announcement_id
announcement_key

source:
  filename
  format
  storage_path
~~~

Request 계약은 일치한다.

정상 Response Schema도 다음 필드가 일치한다.

~~~text
document_id
announcement_id
announcement_key
status
document_format
output_path

summary:
  chunk_count
  embedding_count

key_information:
  application_period
  eligibility
  supply_information
  income_asset_criteria
  required_documents
  winner_announcement
  contact_information
~~~

Python Schema 객체 간 실제 변환 검증도 수행했다.

~~~text
request validation: OK
worker response validation: OK
backend response compatibility: OK
~~~

Document Worker 패키지 전체 문법 검사도 통과했다.

~~~text
python -m compileall document_worker
PASS
~~~

### 현재 상태 변경

이전:

~~~text
Document Worker Endpoint  PENDING
~~~

현재:

~~~text
Document Worker Endpoint  PARTIAL
~~~

여기서 `PARTIAL`은 다음 의미다.

~~~text
Endpoint                     IMPLEMENTED
Request Schema                IMPLEMENTED / MATCHED
Response Schema               IMPLEMENTED / MATCHED
Parser                        IMPLEMENTED
Normalizer                    IMPLEMENTED
Structure / Verification      IMPLEMENTED
Chunking                      IMPLEMENTED

Worker → Embedding HTTP       PENDING
Embedding Artifact            PENDING
Key Information Extraction    PENDING
Completed Runtime Response    PENDING
~~~

Backend Runtime Cutover는 아직 수행하지 않는다.

현재 Backend는 기존 MVP의:

~~~text
DOCUMENT_REPROCESSOR
→ Python callable
~~~

경로를 유지한다.

Worker가 Embedding HTTP 연동과 Key Information Extraction을 완료하고 정상 `completed` Response를 실제로 반환할 수 있게 된 후 Backend Runtime을 `process_document_with_worker()` 경로로 전환한다.

---

## 24. 2026-08-29 Backend Document Runtime 전환 스위치 준비

Document Worker의 전체 처리 완료를 기다리는 동안 Backend Runtime을 즉시 전환하지 않고, 기존 MVP 처리 방식과 Worker HTTP 처리 방식을 선택할 수 있는 Runtime 전환 스위치를 준비했다.

### 변경된 Runtime 구조

기존:

~~~text
Backend
→ pipeline_gateway.reprocess_document()
→ DOCUMENT_REPROCESSOR
→ Python direct call
~~~

변경:

~~~text
Backend
→ pipeline_gateway.reprocess_document()

DOCUMENT_PROCESSING_RUNTIME=legacy
→ DOCUMENT_REPROCESSOR
→ 기존 Python direct call

DOCUMENT_PROCESSING_RUNTIME=worker_http
→ process_document_with_worker()
→ Document Worker HTTP
~~~

기본값은 다음과 같다.

~~~text
DOCUMENT_PROCESSING_RUNTIME=legacy
~~~

환경변수가 설정되지 않은 경우에도 `legacy`를 사용하므로 기존 MVP Runtime 동작은 유지된다.

지원하지 않는 Runtime 값은 `PipelineUnavailableError`로 차단한다.

### 현재 전환 정책

현재 Document Worker는 다음 단계까지 구현되어 있다.

~~~text
Parser
→ Normalizer
→ Structure / Verification
→ Chunking
~~~

다음 단계는 아직 미완료다.

~~~text
Worker → Embedding HTTP
→ Embedding Artifact
→ Key Information Extraction
→ completed Response
~~~

따라서 `worker_http` 실행 경로는 코드 수준에서 준비했지만 실제 Runtime 기본값은 `legacy`로 유지한다.

Worker가 정상 `completed` Response를 반환할 수 있게 된 후:

~~~text
DOCUMENT_PROCESSING_RUNTIME=worker_http
~~~

로 전환하여 실제 통합 검증을 수행한다.

### 검증 결과

신규 Runtime 분기 테스트:

~~~text
legacy runtime                         PASS
worker_http runtime                    PASS
invalid runtime rejection              PASS
~~~

관련 Backend 회귀 테스트:

~~~text
Pipeline Gateway Runtime
Integration Service
Document Processing Service
Pipeline Persistence

28 tests PASS
~~~

전체 Backend 회귀 테스트:

~~~text
Ran 109 tests

PASS: 105
FAIL: 4
~~~

실패 4건은 기존 KeyInformationExtractor 관련 테스트와 동일하다.

~~~text
test_application_period
test_application_period_korean_ampm_range
test_application_period_labeled_range
test_supply_summary_is_compact
~~~

이번 Runtime 전환 작업으로 새로 발생한 Backend 회귀 실패는 없다.

문법 검사:

~~~text
python -m compileall
backend/app/services/pipeline_gateway.py
backend/app/services/document_processing_service.py

PASS
~~~

현재 상태:

~~~text
Backend Runtime Switch           IMPLEMENTED
Legacy Runtime Default           ACTIVE
Worker HTTP Runtime Path         PREPARED
Actual Runtime Cutover           PENDING
~~~

Service API Contract의 구현 상태에서는 Runtime 전환 준비 완료를 `PREPARED`로 관리한다.

---

## 25. 2026-08-29 Backend RAG Runtime 전환 스위치 준비

기존 Backend의 `chat_service.py`는 `RAG_ANSWER_FUNCTION` 환경변수를 통해 Python 함수를 직접 호출하는 구조였다.

API/Docker 서비스 분리를 위해 Backend가 RAG 서비스를 직접 import하지 않고 HTTP 경계만 사용하도록 Runtime 전환 구조를 추가했다.

### 변경된 Runtime 구조

~~~text
RAG_RUNTIME=legacy
→ RAG_ANSWER_FUNCTION
→ 기존 Python direct call

RAG_RUNTIME=rag_http
→ Backend rag_client
→ POST /v1/rag/answer
~~~

기본값은 다음과 같이 유지한다.

~~~text
RAG_RUNTIME=legacy
~~~

환경변수가 설정되지 않은 경우에도 `legacy`를 사용하므로 기존 RAG 실행 동작은 유지된다.

지원하지 않는 Runtime 값은 `RagServiceUnavailableError`로 차단한다.

### HTTP 오류 처리

`rag_client.answer_question()`에서 발생한 `InternalServiceClientError` 계열 오류를 `RagServiceUnavailableError`로 변환하도록 처리했다.

이로 인해 기존 Backend `/chat` 진입점에서 RAG HTTP 서비스 오류를 기존 503 처리 흐름으로 유지할 수 있다.

### 응답 변환

내부 RAG Service 응답인 `RagAnswerResponse`를 외부 사용자 API 응답인 `ChatResponse`로 명시적으로 변환한다.

~~~text
Internal RAG Response
result
answer
grounded
evidence
    ↓
Backend ChatResponse
answer
grounded
evidence
~~~

### 검증 결과

신규 RAG Runtime 분기 테스트:

~~~text
legacy runtime                         PASS
rag_http runtime                       PASS
invalid runtime rejection              PASS
HTTP client error mapping               PASS
~~~

관련 Chat/RAG 테스트:

~~~text
Chat Service Runtime
RAG Client
Backend Chat Contract

27 tests PASS
~~~

전체 Backend 회귀 테스트:

~~~text
Ran 113 tests

PASS: 109
FAIL: 4
~~~

실패 4건은 기존 KeyInformationExtractor 관련 테스트와 동일하다.

~~~text
test_application_period
test_application_period_korean_ampm_range
test_application_period_labeled_range
test_supply_summary_is_compact
~~~

이번 RAG Runtime 전환 작업으로 새로 발생한 Backend 회귀 실패는 없다.

문법 검사:

~~~text
python -m compileall
backend/app/services/chat_service.py
backend/app/clients/rag_client.py

PASS
~~~

현재 상태:

~~~text
Backend RAG Runtime Switch        IMPLEMENTED
Legacy RAG Runtime Default        ACTIVE
Backend RAG HTTP Path             PREPARED
Actual RAG Runtime Cutover        PENDING
RAG Endpoint                      PENDING
~~~

실제 RAG Endpoint가 구현되기 전까지는 `RAG_RUNTIME=rag_http`로 기본값을 전환하지 않는다.

## 26. 2026-08-29 Backend Service Boundary 직접 의존성 정리

Backend API 서비스 분리 기준에 맞춰 Backend가 다른 Service 구현 모듈을 Python import로 직접 참조하는 경로를 추가 점검하고 정리했다.

### 변경 내용

`collection_publish_service.py`는 기존에 RAG 내부 설정 모듈을 직접 참조하고 있었다.

~~~text
Backend
→ rag.retrieval.config.DEFAULT_RETRIEVAL_CONFIG
→ embedding_model_name
~~~

서비스 분리 이후 Backend가 RAG 내부 Python 구현에 의존하지 않도록 해당 참조를 제거했다.

변경 후:

~~~text
Backend
→ backend.app.core.config.Settings
→ embedding_model_name
~~~

`Settings`에 다음 기본 설정을 추가했다.

~~~text
embedding_model_name = BAAI/bge-m3
~~~

따라서 Embedding 모델 이름이 필요한 Backend 검증 로직은 Backend 자체 설정을 사용하며 RAG 구현 모듈을 import하지 않는다.

### Service Boundary 점검

Backend 전체 Python 코드를 기준으로 다음 직접 import를 검색했다.

~~~text
rag
document_worker
services.embedding
pipeline.embedding
~~~

검색 결과:

~~~text
직접 Python import 0건
~~~

기존 MVP 호환을 위해 남아 있는 `RAG_ANSWER_FUNCTION`, `DOCUMENT_REPROCESSOR` 기반 legacy runtime은 실제 Runtime Cutover 전까지 유지한다.

이는 서비스 구현 모듈에 대한 일반 direct import와 별도로 관리한다.

### 검증 결과

관련 Collection Publish 테스트:

~~~text
6 tests PASS
~~~

전체 Backend 회귀 테스트:

~~~text
Ran 113 tests

PASS: 109
FAIL: 4
~~~

실패 4건은 기존 KeyInformationExtractor 관련 테스트와 동일하다.

~~~text
test_application_period
test_application_period_korean_ampm_range
test_application_period_labeled_range
test_supply_summary_is_compact
~~~

이번 Service Boundary 정리로 새로 발생한 Backend 회귀 실패는 없다.

현재 Backend API 분리 상태:

~~~text
Backend HTTP Client                 IMPLEMENTED
Backend Worker Orchestration        IMPLEMENTED
Backend Worker Artifact Persist     IMPLEMENTED
Backend Document Runtime Switch     IMPLEMENTED
Backend RAG Runtime Switch          IMPLEMENTED
Backend Service Boundary Cleanup    IMPLEMENTED

Actual Document Runtime Cutover     PENDING
Actual RAG Runtime Cutover          PENDING
~~~

---

## 27. 2026-08-30 Service Endpoint 통합 및 RAG Runtime Cutover

`develop-api`에 RAG 및 Document Worker의 API 구현이 추가된 이후 Backend 계약과 실제 Runtime 연결을 다시 검증했다.

### Service 구현 통합 상태

다른 Service 담당 영역에서 다음 구현이 `develop-api`에 통합되었다.

~~~text
RAG Endpoint                       IMPLEMENTED
RAG → Embedding HTTP               IMPLEMENTED

Document Worker Endpoint           IMPLEMENTED
Document Worker → Embedding HTTP   IMPLEMENTED
Embedding Artifact 생성            IMPLEMENTED
Key Information Extraction        IMPLEMENTED
Completed Worker Response          IMPLEMENTED
~~~

Backend에서는 기존에 구현한 HTTP Client 및 Orchestration 계약이 위 Service 구현과 호환되는지 집중 회귀 테스트를 수행했다.

초기 통합 검증 결과:

~~~text
Backend focused contract/runtime tests

27 tests PASS
~~~

RAG 기본 Runtime 전환 테스트를 추가한 이후 결과:

~~~text
Backend focused contract/runtime tests

28 tests PASS
~~~

### AWS RAG 실제 E2E 검증

AWS 실행 환경에서 다음 Service의 Health를 확인했다.

~~~text
Embedding Service :18001   PASS
RAG Service       :18002   PASS
llama.cpp         :8080    PASS
~~~

Embedding Service는 다음 모델이 실제 Load된 상태였다.

~~~text
BAAI/bge-m3
~~~

현재 활성 Collection은 다음과 같이 확인했다.

~~~text
active_collection_run_id = 2
~~~

실제 검색 가능한 공고 중 다음 데이터를 검증 대상으로 사용했다.

~~~text
announcement_id = 78
chunk_count      = 614
embedding_count  = 614
~~~

RAG API에 실제 질문을 전송한 결과:

~~~text
result          = grounded
grounded        = true
evidence_count  = 5
~~~

따라서 다음 전체 경로가 실제 AWS 데이터로 동작함을 확인했다.

~~~text
RAG API
→ Embedding Service
→ BGE-M3 Query Embedding
→ PostgreSQL / pgvector
→ Retrieval
→ llama.cpp
→ Answer Generation
→ grounded answer + evidence
~~~

### Backend → RAG 실제 HTTP 검증

동일한 AWS 환경에서 `curl` 직접 호출뿐 아니라 Backend의 `rag_client.answer_question()`을 통해 RAG Service를 호출했다.

결과:

~~~text
RESULT         grounded
GROUNDED       True
EVIDENCE_COUNT 5
~~~

이에 따라 다음 경로를 실제로 검증했다.

~~~text
Backend rag_client
→ HTTP
→ RAG Service
→ Embedding
→ PostgreSQL
→ llama.cpp
→ RAG Response
→ Backend Response Contract Parsing
~~~

### Backend Runtime Switch 실제 검증

마지막으로 Backend Service Layer의 실제 진입점에 다음 Runtime을 적용했다.

~~~text
RAG_RUNTIME=rag_http
RAG_SERVICE_BASE_URL=http://127.0.0.1:18002
~~~

`chat_service.answer_question_via_rag()` 실행 결과:

~~~text
GROUNDED       True
EVIDENCE_COUNT 5
~~~

따라서 다음 Runtime 경로도 실제 AWS에서 검증 완료했다.

~~~text
Backend chat_service
→ RAG_RUNTIME=rag_http
→ Backend rag_client
→ RAG Service
→ Embedding Service
→ PostgreSQL / pgvector
→ llama.cpp
→ Backend
~~~

### RAG 기본 Runtime 전환

AWS 검증 완료 후 API 버전의 Backend 기본 RAG Runtime을 다음과 같이 변경했다.

~~~text
Before
RAG_RUNTIME default = legacy

After
RAG_RUNTIME default = rag_http
~~~

`.env.example` 역시 다음 기준으로 변경했다.

~~~text
RAG_SERVICE_BASE_URL=http://127.0.0.1:18002
RAG_RUNTIME=rag_http
~~~

`127.0.0.1`은 현재 로컬 또는 AWS 동일 호스트 실행 기준이다.

향후 Docker Compose에서는 Backend Container의 `localhost`가 RAG Service를 의미하지 않으므로 Docker Service DNS 주소로 변경해야 한다.

기존 `legacy` Runtime은 제거하지 않고 rollback 경로로 유지한다.

### 현재 상태

~~~text
Backend HTTP Client                 IMPLEMENTED
Backend Worker Orchestration        IMPLEMENTED
Backend Worker Artifact Persist     IMPLEMENTED
Backend Document Runtime Switch     IMPLEMENTED
Backend RAG Runtime Switch          IMPLEMENTED
Backend Service Boundary Cleanup    IMPLEMENTED

Embedding Endpoint                  IMPLEMENTED
RAG Endpoint                        IMPLEMENTED
RAG → Embedding HTTP                IMPLEMENTED
Document Worker Endpoint            IMPLEMENTED
Document Worker → Embedding HTTP    IMPLEMENTED

Actual RAG Runtime Cutover          IMPLEMENTED
Backend → RAG AWS E2E               PASS

Actual Document Runtime Cutover     PENDING
Backend → Worker AWS E2E            PENDING
Docker Compose Integration          PENDING
Overall E2E                         PARTIAL
~~~

다음 단계는 Backend → Document Worker 실제 HTTP 통합 검증 후 Document Runtime을 `worker_http` 기본 경로로 전환하는 것이다.

---

## 28. 2026-08-30 RAG Runtime Cutover 최종 회귀 검증

RAG 기본 Runtime을 `rag_http`로 전환하고, 기존 legacy Runtime 계약 테스트에 `RAG_RUNTIME=legacy`를 명시한 뒤 Backend 전체 회귀 테스트를 다시 수행했다.

최종 결과:

~~~text
Ran 114 tests

PASS: 110
FAIL: 4
ERROR: 0
~~~

실패한 4개 테스트는 API 전환 이전부터 확인된 `KeyInformationExtractor` 관련 테스트와 동일하다.

~~~text
test_application_period
test_application_period_korean_ampm_range
test_application_period_labeled_range
test_supply_summary_is_compact
~~~

RAG Runtime 기본값 변경으로 처음 발생했던 기존 ChatContract 테스트 오류는 legacy Runtime을 명시하도록 테스트 계약을 보정한 뒤 해결되었다.

~~~text
ChatContractTest

2 tests PASS
~~~

따라서 이번 RAG Runtime Cutover로 새로 발생한 Backend 회귀 오류는 없다.

현재 결론:

~~~text
Actual RAG Runtime Cutover      IMPLEMENTED
Backend → RAG AWS E2E           PASS
Backend RAG regression error    0

Actual Document Runtime Cutover PENDING
Backend → Worker AWS E2E        PENDING
~~~

---

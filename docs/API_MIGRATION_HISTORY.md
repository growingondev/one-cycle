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

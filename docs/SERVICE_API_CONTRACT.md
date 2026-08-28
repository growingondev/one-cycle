# DDOKBOT Internal Service API Contract

## 1. 문서 목적

이 문서는 DDOKBOT Docker 서비스 분리 버전에서 서로 다른 Service Container 사이에 사용하는 내부 HTTP API 계약을 정의한다.

대상 브랜치는 `develop-api`이다.

기존 `develop` 브랜치의 MVP 실행 구조는 유지하며, API 서비스 분리 버전에서만 본 계약을 적용한다.

본 계약은 Backend, Document Worker, RAG, Embedding 담당자가 구현 전에 함께 확인한 기준을 기록한다.

---

## 2. 기본 원칙

같은 Service Container 내부의 모듈은 기존 Python import, 함수 호출, subprocess, File I/O 방식을 사용할 수 있다.

서로 다른 Service Container 경계를 넘는 통신은 HTTP API 또는 서비스 간 합의된 표준 방식으로 처리한다.

목표 구조는 다음과 같다.

~~~text
Frontend
    ↓ HTTP
Backend
    ├─ HTTP → Document Worker
    ├─ HTTP → RAG
    └─ PostgreSQL

Document Worker
    ├─ Parser
    ├─ Normalizer
    ├─ Structure / Verification
    ├─ Chunking
    ├─ HTTP → Embedding
    └─ Key Information Extraction

RAG
    ├─ HTTP → Embedding
    ├─ PostgreSQL Retrieval
    └─ HTTP → llama.cpp
~~~

Backend는 Embedding Service를 직접 호출하지 않는다.

~~~text
Document Worker ──HTTP──→ Embedding
RAG             ──HTTP──→ Embedding
Backend         ─────X──→ Embedding
~~~

---

## 3. 공통 Internal Service Error Contract

Service에서 HTTP 오류를 반환할 때 다음 형식을 사용한다.

~~~json
{
  "error": {
    "code": "SERVICE_ERROR_CODE",
    "message": "Error message."
  }
}
~~~

호출 측은 다음 정보를 유지한다.

- HTTP status code
- error code
- error message

---

# 4. Document Worker API

## 4.1 Endpoint

~~~text
POST /v1/documents/{document_id}/process
~~~

현재 구현은 우선 동기 HTTP 방식을 기준으로 한다.

Backend의 초기 Worker timeout 기준은 600초이다.

실제 Docker 환경에서 처리시간을 측정한 후 장시간 실행으로 문제가 발생할 경우에만 `202 Accepted + job_id` 기반 비동기 처리를 추후 검토한다.

현재 MVP 계약에는 Queue를 포함하지 않는다.

---

## 4.2 Backend → Document Worker Request

~~~json
{
  "announcement_id": 1,
  "announcement_key": "announcement_001",
  "source": {
    "filename": "announcement.hwpx",
    "format": "hwpx",
    "storage_path": "/data/documents/announcement_001/announcement.hwpx"
  }
}
~~~

### Path Parameter

| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| `document_id` | integer | 1 이상의 DB Document ID |

### Request Body

| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| `announcement_id` | integer | 1 이상의 DB Announcement ID |
| `announcement_key` | string | 빈 문자열 불가 |
| `source.filename` | string | 빈 문자열 불가 |
| `source.format` | string | `hwp` 또는 `hwpx` |
| `source.storage_path` | string | Worker가 접근 가능한 shared volume 경로 |

Backend는 DB에 저장된 Document Context를 기준으로 위 Request를 구성한다.

---

## 4.3 Document Worker 책임

Document Worker는 다음 처리까지만 수행한다.

~~~text
Parser
→ Normalizer
→ Structure / Verification
→ Chunking
→ Embedding Service 호출
→ Key Information Extraction
→ Artifact 생성
→ Backend에 처리 결과 반환
~~~

Document Worker는 Backend DB Persistence를 직접 수행하지 않는다.

Document Worker는 ProcessingRun을 생성, 활성화 또는 상태 변경하지 않는다.

Document Worker는 Key Information을 Backend DB에 직접 저장하지 않는다.

---

## 4.4 Artifact 처리

Artifact 파일 자체를 HTTP Response Body에 포함하지 않는다.

Worker는 shared output volume에 기존 Artifact 구조를 생성한다.

예:

~~~text
/data/outputs/
└─ {announcement_key}/
   └─ document_{document_id}/
      ├─ 01_parsed/
      ├─ 02_normalized/
      ├─ 03_structured/
      ├─ 04_chunks/
      └─ 05_embeddings/
~~~

Backend는 Worker Response의 `output_path`를 기준으로 Artifact를 검증하고 Persistence한다.

현재 Persistence에서 필요한 주요 Artifact는 다음과 같다.

~~~text
step4-1_value_normalized.json
step4-3_verification.json
chunks.json
metadata.json
embeddings.npy
~~~

Embedding report 등의 부가 Artifact는 필수 Persistence 계약과 분리한다.

---

## 4.5 성공 Response

~~~json
{
  "document_id": 1,
  "announcement_id": 1,
  "announcement_key": "announcement_001",
  "status": "completed",
  "document_format": "hwpx",
  "output_path": "/data/outputs/announcement_001/document_1",
  "summary": {
    "chunk_count": 100,
    "embedding_count": 100
  },
  "key_information": {
    "application_period": {},
    "eligibility": {},
    "supply_information": {},
    "income_asset_criteria": {},
    "required_documents": {},
    "winner_announcement": {},
    "contact_information": {}
  }
}
~~~

### Response 규칙

- `status`는 성공 시 `completed`
- `document_format`은 `hwp` 또는 `hwpx`
- `output_path`는 빈 문자열 불가
- `summary.chunk_count`는 0 이상
- `summary.embedding_count`는 0 이상
- Key Information 7개 필드는 모두 존재해야 함

---

## 4.6 Key Information Contract

필수 필드:

~~~text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
~~~

각 필드는 객체 형식이어야 한다.

다음 결과는 정상 처리로 인정한다.

~~~json
{
  "status": "not_found"
}
~~~

`not_found`는 추출 로직이 정상적으로 실행되었지만 원문에서 해당 정보를 찾지 못했다는 의미이다.

따라서 개별 필드가 `not_found`여도 Worker 전체 처리는 성공할 수 있다.

반면 다음은 성공 Response로 인정하지 않는다.

- 필수 7개 필드 중 하나 이상 누락
- 필드 타입 오류
- Key Information Extractor 실행 실패
- Worker Response Schema 불일치

---

## 4.7 Backend 책임

Worker가 성공 결과를 반환하면 Backend가 다음을 담당한다.

~~~text
Worker Response 검증
→ output_path 기준 Artifact 검증
→ Artifact DB Persistence
→ Embedding DB Persistence
→ Key Information DB 저장
→ ProcessingRun 상태 처리
→ 정상 결과 활성화
~~~

Worker 호출 또는 Persistence 과정에서 발생하는 Backend 운영 오류 기록 역시 Backend 책임이다.

---

# 5. RAG API

## 5.1 Endpoint

~~~text
POST /v1/rag/answer
~~~

---

## 5.2 Backend → RAG Request

~~~json
{
  "announcement_id": 1,
  "question": "신청 기간은 언제인가요?"
}
~~~

### Request 규칙

| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| `announcement_id` | integer | 1 이상의 DB Announcement ID |
| `question` | string | trim 후 빈 문자열 불가 |

RAG는 전달받은 `announcement_id`에 해당하는 공고 범위 안에서 Retrieval을 수행한다.

---

## 5.3 RAG 처리 흐름

~~~text
question
→ Embedding Service
→ Query Vector
→ Vector Search + BM25
→ RRF
→ Evidence 구성
→ llama.cpp
→ Answer
~~~

현재 RAG Retrieval은 Vector Search와 BM25 결과를 RRF로 결합한다.

Reranker는 현재 계약에 포함하지 않는다.

---

## 5.4 성공 Response

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

Business Result는 다음 세 가지를 허용한다.

~~~text
grounded
no_evidence
unsupported
~~~

`no_evidence`와 `unsupported`는 Service 장애가 아니라 정상적인 Business Result이다.

---

## 5.5 Evidence Contract

| 필드 | 타입 | 비고 |
| --- | --- | --- |
| `chunk_id` | string 또는 integer | 근거 Chunk 식별자 |
| `section_title` | string 또는 null | 근거 Section |
| `content` | string | 근거 원문 |
| `score` | number 또는 null | 검색 점수 |

Backend 외부 Chat API의 camelCase 계약과 내부 RAG Service의 snake_case 계약은 분리한다.

Backend Service Layer가 두 계약 사이의 Adapter 역할을 담당한다.

---

# 6. Embedding API

## 6.1 Endpoint

~~~text
POST /v1/embeddings
~~~

Document Worker의 Chunk Embedding과 RAG의 Query Embedding이 동일 Endpoint를 사용한다.

---

## 6.2 Request

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

### Request 규칙

- `items`는 최소 1개 이상이어야 한다.
- `items[].id`는 Request 내에서 중복될 수 없다.
- `items[].text`는 빈 문자열일 수 없다.
- 호출자는 각 입력을 식별할 수 있는 `id`를 제공해야 한다.

Document Worker 예:

~~~json
{
  "items": [
    {
      "id": "chunk-001",
      "text": "첫 번째 청크"
    },
    {
      "id": "chunk-002",
      "text": "두 번째 청크"
    }
  ]
}
~~~

RAG Query 예:

~~~json
{
  "items": [
    {
      "id": "query",
      "text": "신청 기간은 언제인가요?"
    }
  ]
}
~~~

---

## 6.3 Response

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

### Response 규칙

- Response 배열 순서에 의존하지 않는다.
- Request와 Response는 `id` 기준으로 매칭한다.
- 성공 Response에는 Request에서 전달한 모든 `id`가 정확히 1개씩 존재해야 한다.
- Request에 없던 추가 `id`를 성공 결과로 반환하지 않는다.
- 각 `embedding`은 Service가 선언한 `dimension`과 일치해야 한다.

현재 기준 모델:

~~~text
BAAI/bge-m3
dimension = 1024
normalized = true
~~~

---

## 6.4 Embedding Service 책임

Embedding Service는 다음만 담당한다.

~~~text
입력 검증
→ Embedding Model 실행
→ 결과 검증
→ id + vector 반환
~~~

Embedding Service는 Chunk 또는 Document Metadata를 DB에 저장하지 않는다.

Embedding Service는 PostgreSQL에 직접 Persistence하지 않는다.

호출 측인 Document Worker 또는 RAG가 원래 Context를 보유하고 `id` 기준으로 결과를 다시 연결한다.

---

# 7. Shared Volume Contract

Backend와 Document Worker는 원본 문서와 처리 Artifact를 동일한 Container 내부 절대 경로로 접근할 수 있어야 한다.

기준 경로:

~~~text
/data/documents
/data/outputs
~~~

Docker Compose 통합 시 Backend와 Document Worker에 동일 volume을 mount한다.

예:

~~~text
Backend
├─ /data/documents
└─ /data/outputs

Document Worker
├─ /data/documents
└─ /data/outputs
~~~

Backend가 Worker Request에 전달한:

~~~text
/data/documents/...
~~~

경로는 Worker Container에서도 동일 경로로 접근 가능해야 한다.

Worker가 Response로 반환한:

~~~text
/data/outputs/...
~~~

경로 역시 Backend Container에서 동일 경로로 접근 가능해야 한다.

실제 Docker volume 이름과 host mount 위치는 Docker Compose 통합 단계에서 확정한다.

---

# 8. Service Responsibility Summary

| 영역 | Backend | Document Worker | RAG | Embedding |
| --- | --- | --- | --- | --- |
| Document DB Context | O | X | X | X |
| Parser / Normalizer | X | O | X | X |
| Structure / Verification | X | O | X | X |
| Chunking | X | O | X | X |
| Chunk Embedding 요청 | X | O | X | - |
| Query Embedding 요청 | X | X | O | - |
| Embedding Model 실행 | X | X | X | O |
| Artifact 생성 | X | O | X | X |
| Artifact DB Persistence | O | X | X | X |
| Key Information Extraction | X | O | X | X |
| Key Information DB 저장 | O | X | X | X |
| ProcessingRun 관리 | O | X | X | X |
| Retrieval | X | X | O | X |
| LLM 호출 | X | X | O | X |

---

# 9. 구현 상태

현재 계약 상태:

~~~text
Document Worker Contract  CONFIRMED
RAG Contract              CONFIRMED
Embedding Contract        CONFIRMED
Shared Volume Direction   CONFIRMED
~~~

현재 구현 상태:

~~~text
Backend HTTP Client               IMPLEMENTED
Backend Worker Orchestration      IMPLEMENTED
Backend Worker Artifact Persist   IMPLEMENTED

Document Worker Endpoint          PENDING
RAG Endpoint                      PENDING
Embedding Endpoint                IMPLEMENTED

Backend Runtime Cutover           PENDING
Docker Compose Integration        PENDING
E2E                               PENDING
~~~

계약 확정과 Endpoint 구현 완료는 서로 다른 상태로 관리한다.

---

# 10. Runtime 전환 원칙

각 Service Endpoint가 실제로 준비되기 전까지 기존 MVP의 Python direct call을 제거하지 않는다.

현재:

~~~text
Backend → RAG
RAG_ANSWER_FUNCTION
→ Python callable

Backend → Document Processing
DOCUMENT_REPROCESSOR
→ Python callable
~~~

Service Endpoint가 구현되고 단위 테스트 및 통합 테스트가 가능해지면 `develop-api`에서 HTTP Client 호출로 전환한다.

기존 `develop` 브랜치의 MVP Runtime은 API/Docker 전환 완료 전까지 유지한다.

---

# 11. Docker 통합 시 확인 항목

- Service hostname 및 port 확정
- Container 간 `localhost` 사용 금지
- `/data/documents` shared volume
- `/data/outputs` shared volume
- Backend → Document Worker 연결
- Backend → RAG 연결
- Document Worker → Embedding 연결
- RAG → Embedding 연결
- RAG → llama.cpp 연결
- PostgreSQL 접근 경계 확인
- 실제 Worker 처리시간 측정
- Timeout 검증
- 전체 E2E 검증

---

# 12. 계약 변경 규칙

본 문서의 Request/Response Schema를 변경해야 하는 경우 호출 측과 제공 측이 함께 확인한 후 변경한다.

특히 다음 변경은 단독으로 진행하지 않는다.

- Endpoint path 변경
- 필수 Request 필드 변경
- 필수 Response 필드 변경
- Key Information 7개 필드 변경
- Embedding Request/Response ID 규칙 변경
- Shared Volume 경로 규칙 변경
- 동기 HTTP에서 비동기 Job 방식으로 변경

계약 변경 시 관련 Client, Service, Test 및 `API_MIGRATION_HISTORY.md`를 함께 갱신한다.

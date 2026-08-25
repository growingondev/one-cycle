# Backend / DB 코드 가이드

> 기준 시점: **2026-08-25**
> 기준: `develop` 최신 통합 코드 + AWS EC2 실제 E2E 검증 결과
> 목적: 현재 Backend / DB의 역할, 실제 연결 구조, 운영 기준과 인수인계 지점을 설명한다.
>
> 과거 작업 과정은 `docs/BACKEND_DB_INTEGRATION_HISTORY.md`를 참고한다.

---

# 1. Backend / DB의 책임

Backend / DB는 Crawler, HWP/HWPX Parser, Chunking, Embedding, LLM 알고리즘 자체를 구현하는 영역이 아니다.

현재 책임은 다음과 같다.

- FastAPI 사용자 / 관리자 API
- PostgreSQL + pgvector 데이터 모델과 DB Session
- Crawler 결과 검증 및 Persistence
- Document Role 분류
- 외부 Pipeline callable Gateway
- 문서 처리 산출물 Persistence
- ProcessingRun / ChunkSet active 상태 관리
- KeyInformation 저장
- Collection Publish / Active Collection 관리
- ErrorLog 공통 저장
- 관리자 인증 / 세션
- 사용자 서비스와 RAG가 사용할 서비스 데이터 경계 제공

---

# 2. 현재 Runtime/API 구조

```text
사용자 Frontend ─┐
                 ├→ FastAPI /api
관리자 Frontend ─┘
                    │
        ┌───────────┼───────────────┐
        │           │               │
        ▼           ▼               ▼
announcement    chat_service     admin routes
 service           │               │
        │       rag.service     ┌───┴────────────┐
        │           │           │                │
        │      DBRAGPipeline admin_service  pipeline_gateway
        │           │           │                │
        │      BGE-M3 Query     │        ┌───────┴────────┐
        │       Embedding       │        │                │
        │           │           │   Integration       Document
        │      pgvector         │     Service         Processor
        │           │           │        │
        │     generate_answer   │  Collection Service
        │           │           │        │
        │       llama.cpp       │      Crawler
        │           │           │
        └───────────┴───────────┴────────────→ PostgreSQL + pgvector
```

주의:

- `pipeline_gateway`는 환경변수에 등록된 callable을 로드하는 경계다.
- Gateway 내부에 Crawler / Parser 알고리즘이 들어 있는 것이 아니다.
- Collection Publish는 별도 Service이며 현재 관리자 API에 Publish endpoint는 없다.

---

# 3. 현재 Gateway / Integration 계약

`.env.example` 기준:

```env
COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
ANNOUNCEMENT_RECOLLECTOR=backend.app.services.integration_service:recollect_persist_and_process
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document
RAG_ANSWER_FUNCTION=rag.service:answer_question
```

현재 `ERROR_RETRY_RUNNER`는 연결되지 않았다.

## 전체 수집

```text
Admin API
→ pipeline_gateway.collect_announcements()
→ Integration Service
→ Collection Service
→ Crawler
→ Crawler Result
→ Collection Service Persistence
→ CollectionRun
→ Announcement
→ Document Role Classification
→ Document
→ analysis_document_ids
→ Integration Service
→ pipeline_gateway.reprocess_document()
→ DOCUMENT_REPROCESSOR
→ Document Processor
```

## 개별 재수집

```text
Admin API
→ pipeline_gateway.recollect_announcement()
→ Integration Service
→ Collection Service recollect
→ 새 Document 저장
→ new_analysis_document_ids
→ Document Processor
```

## 개별 문서 재처리

```text
POST /api/admin/documents/{document_id}/reprocess
→ pipeline_gateway.reprocess_document()
→ DOCUMENT_REPROCESSOR
→ pipeline.document_processor:reprocess_document
```

---

# 4. Document Role

현재 Role:

```text
primary
supporting
unknown
```

현재 분류는 `backend/app/services/document_role_service.py`의 **파일명 keyword 규칙**을 사용한다.

현재 브랜치에서는 실제 LH 데이터에서 확인된 일반 `제출서류` 패턴도 supporting으로 분류한다.

## 현재 처리 정책

| Role | DB 저장 | 전체 문서 처리 | KeyInformation | RAG |
|---|---:|---:|---:|---:|
| primary | O | O | O | O |
| supporting | O | X | X | X |
| unknown | O | X | X | X |

현재 `collection_service.py`는 다음 문서만 `analysis_document_ids`에 포함한다.

```text
document_role == primary
AND
download_status == completed
```

Publish 시:

- primary: ProcessingRun / Verification / ChunkSet / Chunk / Embedding 검증
- supporting: 별도 AI 처리 검증 없음
- unknown: 존재하면 Publish 실패

## 현재 한계

Role과 처리 정책이 결합되어 있기 때문에 supporting 문서는 현재 RAG에서 제외된다.

향후 방향은 **Document Role과 Processing Policy를 분리**하는 것이다.

```text
primary
→ Structure
   ├→ KeyInformation
   └→ Chunk → Embedding → RAG

supporting
→ Structure
   └→ Chunk → Embedding → RAG

unknown
→ 추가 판별
→ primary/supporting 재분류
→ 미해결 시 관리자 검토
```

이 방향은 **현재 구현 상태가 아니라 후속 개선 방향**이다.

---

# 5. 문서 처리 실제 실행 순서

현재 `pipeline.document_processor:reprocess_document`의 물리적 실행 순서:

```text
Document
→ Parser
→ Normalizer
→ Structure + Verification
→ Chunking
→ Embedding
→ persist_document_outputs()
→ ProcessingRun / DocumentStructure / ChunkSet / Chunk / Embedding 저장
→ KeyInformation 추출 / 저장
→ activate_processing_run()
```

## KeyInformation의 논리적 의존성

KeyInformation은 Chunk / Embedding을 입력으로 만들지 않는다.

```text
Structure + Verification
├→ KeyInformation
└→ Chunking → Embedding
```

현재 실행 순서에서 KeyInformation이 Persistence 뒤에 있는 이유는
`source_processing_run_id`를 저장하기 위해 현재 ProcessingRun ID가 필요하기 때문이다.

---

# 6. ProcessingRun / ChunkSet

새 Pipeline 결과가 생성됐다고 기존 정상 데이터를 즉시 교체하지 않는다.

```text
기존 ProcessingRun
is_active = true

새 처리 결과
is_active = false
      ↓
Persistence / 검증 성공
      ↓
KeyInformation 저장 성공
      ↓
activate_processing_run()
      ↓
기존 active 해제
새 ProcessingRun + ChunkSet active
```

대표 정상 조건:

```text
ProcessingRun.execution_status = succeeded
ProcessingRun.verification_status = pass
ProcessingRun.is_active = true

ChunkSet.status = completed
ChunkSet.is_active = true
```

신규 처리 실패 시 기존 정상 active 결과를 보호한다.

---

# 7. Collection Publish

주요 함수:

```python
validate_collection_run_for_publish(collection_run_id)
publish_collection_run(collection_run_id)
```

`validate_collection_run_for_publish()`는 DB를 변경하지 않는다.

`publish_collection_run()`은 내부에서 같은 validation을 수행한 뒤:

```text
system_state.active_collection_run_id
```

를 변경한다.

`CollectionRun` 자체에는 현재 다음 column이 없다.

```text
is_published
published_at
```

따라서 Publish의 현재 의미는 **SystemState의 active Collection 전환**이다.

## Primary Publish 검증

```text
download_status = completed
active ProcessingRun 존재
ProcessingRun.execution_status = succeeded
ProcessingRun.verification_status = pass
active ChunkSet 존재
ChunkSet.status = completed
실제 Chunk 수 > 0
ChunkSet.chunk_count = 실제 Chunk 수
모든 Chunk.status = completed
모든 Chunk에 completed Embedding 존재
Embedding model 일치
dimension = 1024
normalized = true
```

Collection 수준:

```text
CollectionRun.status = success
failed_announcement_count = 0
수집 count 정합성
unknown Document 없음
```

현재 Publish는 관리자 UI/API에서 직접 실행하지 않는다.

전체 신규 수집 경로에서는 `collect_persist_and_process()`가 다음 조건을 모두 만족할 때 `publish_collection_run(collection_run_id)`을 자동 호출한다.

```text
CollectionRun.status = success
analysis_document_ids 처리 failed_count = 0
```

`analysis_document_ids`는 `primary + download completed` 분석 대상 문서다.

Collection 자체가 실패하거나 분석 대상 Document 처리에 실패가 있으면 Publish를 수행하지 않는다.

Publish validation 또는 active Collection 전환에 실패하면 ErrorLog를 기록하고 Integration 결과를 `failed`로 반환한다.

개별 공고 재수집(`recollect_persist_and_process`)은 자동 Publish하지 않는다.

---

# 8. 사용자 API와 Active Collection

사용자 Announcement API는 `system_state.active_collection_run_id`를 기준으로 현재 서비스 Collection을 제한한다.

RAG도 Active Collection 안에서 요청된 `announcement_id`의 Chunk만 검색한다.

관리자 조회 API는 운영 데이터를 보기 위한 것이므로 Active Collection으로 제한되지 않는다.

---

# 9. RAG DB 조회 경계

현재 Runtime Retrieval:

```text
Question
→ BGE-M3 Query Embedding
→ PostgreSQL + pgvector
→ Active Collection 내 선택 Announcement Top-K
→ generate_answer()
→ llama.cpp
→ Answer + Evidence
```

주요 SQL 필터:

```text
SystemState.active_collection_run_id
요청 announcement_id
ProcessingRun.is_active = true
ChunkSet.is_active = true
Chunk.status = completed
Embedding.status = completed
Embedding.model_name = 현재 Query Embedding Model
Embedding.dimension = 1024
Embedding.normalized = true
Embedding.embedding IS NOT NULL
```

---

# 10. ErrorLog

공통 저장 진입점:

```python
backend.app.services.error_log_service.record_error(...)
```

반환 key:

```text
error_id
```

Integration Service는 문서 처리 실패를 ErrorLog에 기록한다.

지원 error type:

```text
collection
download
parsing
normalizing
structuring
verification
chunking
embedding
database
rag
llm
```

`processing_run_id`, `document_id`, `announcement_id`, `collection_run_id`가 전달되면 DB 관계를 검증하고 상위 링크를 보완한다.

---

# 11. 주요 API

## 사용자

```text
GET  /api/announcements
GET  /api/announcements/{id}
POST /api/chat
```

## 관리자

```text
공고
GET  /api/admin/announcements
POST /api/admin/announcements/collect
GET  /api/admin/announcements/{id}
POST /api/admin/announcements/{id}/recollect

문서
GET  /api/admin/documents
GET  /api/admin/documents/{id}
GET  /api/admin/documents/{id}/download
POST /api/admin/documents/{id}/reprocess

처리
GET  /api/admin/processing-runs

오류
GET   /api/admin/errors
GET   /api/admin/errors/{id}
PATCH /api/admin/errors/{id}/status
POST  /api/admin/errors/{id}/retry
```

주의:

- Backend에는 `/api/admin/processing-runs`가 있지만 현재 관리자 Frontend에 별도 처리이력 페이지는 없다.
- Collection Publish용 관리자 API는 현재 없다.

---

# 12. AWS 실제 E2E 검증

2026-08-25 실제 LH 데이터 기준:

```text
Announcement       50
Document           88
primary            48
supporting         40
unknown             0
```

문서 처리:

```text
requested_count = 48
success_count   = 48
failed_count    = 0
```

저장 결과:

```text
Chunk       14,047
Embedding   14,047
```

Embedding 기준:

```text
model       BAAI/bge-m3
dimension   1024
CUDA        NVIDIA L4
```

Collection 전환:

```text
CollectionRun id = 1
SystemState.active_collection_run_id = 1
```

사용자 화면:

```text
공고 목록 PASS
공고 상세 PASS
KeyInformation 표시 PASS
원문 연결 PASS
```

관리자 화면:

```text
로그인 / 세션 PASS
공고 목록 / 상세 PASS
문서 목록 / 상세 PASS
HWP/HWPX 다운로드 PASS
Error 목록 / 상세 PASS
Error status write PASS
```

## 단일 Document 재처리

실제 `document_id=87`:

```text
기존 ProcessingRun id=48 → inactive
신규 ProcessingRun id=49 → succeeded / pass / active
```

Parser부터 CUDA Embedding, DB Persistence, KeyInformation, Activation까지 실제 Runtime에서 통과했다.

---

# 13. 테스트 기준

현재 `feature/backend-db-update`에서 Backend / DB 핵심 suite:

```text
48 / 48 PASS
```

포함:

```text
Backend contracts
Collection publish
Document role
Integration service
```

`tests/backend` 전체 discover는 현재 develop 기준 KeyInformation `application_period` 관련 기존 실패 3건이 존재한다.

```text
Ran 49
failures = 3
```

이 3건은 이번 `제출서류` Role 수정으로 발생한 회귀가 아니며,
별도 KeyInformation / 문서 처리 영역에서 정리해야 한다.

---

# 14. 현재 외부 연동 제약

다음 값은 repository RAG 코드가 실제로 사용 중이므로 Backend/DB 브랜치에서 임의 삭제하지 않는다.

```text
MVP_ANNOUNCEMENT_ID
MVP_DOCUMENT_FORMAT
LLAMA_MODEL
```

현재 RAG 코드에는 `MVP_ANNOUNCEMENT_ID`, `MVP_DOCUMENT_FORMAT` 기반의 제한 로직이 일부 남아 있다. `LLAMA_MODEL`은 환경변수로 설정하며 현재 `.env.example`은 `gemma`를 사용한다.
이는 Backend/DB 문서 최신화와 별개인 RAG/Chat 후속 정리 대상이다.

---

# 15. Source of Truth

| 영역 | 기준 |
|---|---|
| FastAPI App | `backend/app/main.py`, `backend/app/api/router.py` |
| 사용자 Announcement | `backend/app/services/announcement_service.py` |
| Collection | `backend/app/services/collection_service.py` |
| Integration | `backend/app/services/integration_service.py` |
| Gateway | `backend/app/services/pipeline_gateway.py` |
| Persistence | `backend/app/services/pipeline_persistence.py` |
| Publish | `backend/app/services/collection_publish_service.py` |
| Document Role | `backend/app/services/document_role_service.py` |
| ErrorLog | `backend/app/services/error_log_service.py` |
| ORM | `backend/app/models/` |
| RAG SQL | `rag/db_pipeline.py` |
| Document Processor | `pipeline/document_processor.py` |
| Migration | `migrations/versions/` |

---

# 16. Git / 배포 운영 원칙

```text
Windows 로컬
→ 코드 수정
→ 테스트
→ 문서 수정
→ commit / push / PR

AWS
→ develop pull
→ Runtime 실행
→ 실제 E2E 검증
```

AWS 서버를 코드 작성 / push 기준 저장소로 사용하지 않는다.

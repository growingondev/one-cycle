# Backend / DB 인수인계 가이드

> 기준 시점: **2026-08-27**
>
> 기준 브랜치: `develop`
>
> 기준 커밋: `1c3b2e9`
>
> 목적: Backend/API와 DB 파트를 처음 보는 개발자가 이 문서만으로 현재 구조를 이해하고, 실행·수정·장애 확인·Docker 분리 준비까지 이어갈 수 있도록 한다.
>
> 과거 작업 과정은 `docs/BACKEND_DB_INTEGRATION_HISTORY.md`, 실제 AWS 검증 기록은 `docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md`를 참고한다.
>
> **중요:** 이 문서는 현재 구현(AS-IS)과 Docker 분리 목표(TO-BE)를 구분한다. Docker 목표 구조를 현재 구현된 것으로 해석하면 안 된다.

---

# 1. 담당 파트 개요

Backend / DB 파트는 사용자·관리자 Frontend와 Crawler / Document Processing / RAG 사이의 서비스 경계를 제공하고, 서비스 상태와 처리 결과를 PostgreSQL + pgvector에 저장·조회하는 역할을 담당한다.

현재 Backend / DB의 주요 책임은 다음과 같다.

- FastAPI 사용자 API
- FastAPI 관리자 API
- 관리자 인증 / 세션
- PostgreSQL + pgvector 연결
- SQLAlchemy Session / ORM
- Alembic Migration
- Crawler 결과 검증 및 DB Persistence
- `CollectionRun → Announcement → Document` 저장
- Document Role 분류
- Document Processing 호출 연결
- Pipeline 산출물 DB Persistence
- `ProcessingRun / ChunkSet` active 상태 관리
- KeyInformation 저장 및 조회
- Collection Publish / Active Collection 관리
- ErrorLog 공통 저장
- Glossary CRUD / 조회
- RAG 호출 경계 제공
- 평가용 임시 DB Workflow 제공

Backend / DB는 HWP/HWPX Parser, Normalizer, Structure, Chunking, Embedding, Retrieval, LLM Generation 알고리즘 자체를 구현하는 파트가 아니다.

다만 현재 프로젝트는 아직 완전히 서비스 단위로 분리되지 않았기 때문에 Backend가 이 모듈들을 **Python import / callable 방식으로 직접 호출하는 연결 코드**를 포함하고 있다.

---

# 2. 구현한 기능

## 2.1 사용자 API

```text
GET  /api/announcements
GET  /api/announcements/{announcement_id}
POST /api/chat
GET  /api/glossary
```

## 2.2 관리자 API

```text
GET  /api/admin/announcements
POST /api/admin/announcements/collect
GET  /api/admin/announcements/{id}
POST /api/admin/announcements/{id}/recollect

GET  /api/admin/documents
GET  /api/admin/documents/{id}
GET  /api/admin/documents/{id}/download
POST /api/admin/documents/{id}/reprocess

GET  /api/admin/processing-runs

GET   /api/admin/errors
GET   /api/admin/errors/{id}
PATCH /api/admin/errors/{id}/status
POST  /api/admin/errors/{id}/retry

GET    /api/admin/glossary
POST   /api/admin/glossary
PUT    /api/admin/glossary/{id}
PATCH  /api/admin/glossary/{id}/status
DELETE /api/admin/glossary/{id}
```

## 2.3 Collection 저장 / Publish

```text
Crawler
→ CollectionRun
→ Announcement
→ Document
→ primary Document Processing
→ Processing / Chunk / Embedding 저장
→ KeyInformation 저장
→ ProcessingRun 활성화
→ Publish
→ SystemState.active_collection_run_id 전환
```

서비스 공개 상태는 `system_state.active_collection_run_id`로 관리한다.

## 2.4 Document Processing Persistence

```text
Document
→ ProcessingRun
→ DocumentStructure
→ ChunkSet
→ Chunk
→ Embedding
```

같은 Document를 재처리해도 기존 정상 데이터를 즉시 덮어쓰지 않고, 새 결과가 정상 검증·저장된 뒤 active 상태를 전환한다.

## 2.5 KeyInformation

현재 필수 필드:

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

## 2.6 ErrorLog

공통 진입점:

```python
backend.app.services.error_log_service.record_error(...)
```

반환 식별자:

```text
error_id
```

## 2.7 Glossary

Glossary는 Collection snapshot과 독립된 운영 데이터다.

## 2.8 평가용 임시 DB Workflow

운영 DB와 평가 데이터를 분리하기 위해 다음 평가 DB를 사용할 수 있다.

```text
one_cycle_evaluation_tmp
```

관련 파일:

```text
backend/app/services/evaluation_service.py
backend/app/services/evaluation_pipeline_service.py
backend/scripts/evaluation/create_evaluation_db.py
backend/scripts/evaluation/drop_evaluation_db.py
docs/BACKEND_DB_EVALUATION_WORKFLOW.md
```

---

# 3. 전체 동작 흐름

## 3.1 사용자 공고 목록

```text
User Frontend
↓ HTTP
GET /api/announcements
↓
backend/app/api/routes/announcements.py
get_announcements()
↓ Python call
backend/app/services/announcement_service.py
list_active_announcements()
↓ DB
PostgreSQL
↓
Active Collection의 Announcement 목록
↓ HTTP JSON
User Frontend
```

## 3.2 사용자 공고 상세

```text
User Frontend
↓ HTTP
GET /api/announcements/{announcement_id}
↓
backend/app/api/routes/announcements.py
get_announcement()
↓ Python call
backend/app/services/announcement_service.py
get_active_announcement()
↓ DB
Announcement + Document metadata + KeyInformation
↓
AnnouncementDetailResponse
↓ HTTP JSON
User Frontend
```

현재 사용자 상세 응답의 `documents`에는 다음 메타데이터만 포함된다.

```text
id
originalFilename
documentFormat
downloadStatus
fileSizeBytes
createdAt
```

**현재 사용자 상세 API에는 원본 파일을 직접 열 수 있는 `downloadUrl` 필드가 없다.**

`detailUrl`은 원본 HWP/HWPX 파일 URL이 아니라 LH 공고 상세 페이지 URL이다.

관리자 전용 다운로드 Endpoint는 존재한다.

```text
GET /api/admin/documents/{document_id}/download
```

## 3.3 사용자 Chat

```text
frontend/user/.../DetailScreen.tsx
↓ HTTP POST
/api/chat
↓
backend/app/api/routes/chat.py
chat()
↓ Python call
backend/app/services/chat_service.py
answer_question_via_rag()
↓ importlib / Python callable
RAG_ANSWER_FUNCTION
= rag.service:answer_question
↓
rag/service.py
answer_question()
↓
DBRAGPipeline.ask()
↓
Hybrid Search
├→ Vector Search
└→ Keyword Search
↓
RRF
↓
Generation
↓ HTTP
llama.cpp /v1/chat/completions
↓
Answer + Evidence
↓
ChatResponse
↓ HTTP JSON
Frontend
```

Request:

```json
{
  "announcementId": 1,
  "question": "신청 기간이 언제야?"
}
```

Response:

```json
{
  "answer": "...",
  "grounded": true,
  "evidence": [
    {
      "chunkId": "...",
      "sectionTitle": "...",
      "content": "...",
      "score": 0.0
    }
  ]
}
```

## 3.4 관리자 전체 수집

현재 `POST /api/admin/announcements/collect`는 Queue에 넣는 구조가 아니라 Backend 요청 처리 중 Python callable을 직접 호출한다.

```text
Admin Frontend
↓ HTTP
POST /api/admin/announcements/collect
↓
backend/app/api/routes/admin.py
run_collection()
↓ Python call
pipeline_gateway.collect_announcements()
↓ importlib
COLLECTION_RUNNER
↓
integration_service.collect_persist_and_process()
↓
collection_service.collect_and_persist()
↓ Python import
crawler.crawler.crawl_lh_notices()
↓
Crawler Result
↓
persist_collection_result()
↓ DB
CollectionRun / Announcement / Document
↓
analysis_document_ids
↓
process_document_ids()
↓
pipeline_gateway.reprocess_document()
↓ importlib
DOCUMENT_REPROCESSOR
↓
pipeline.document_processor.reprocess_document()
↓
Document Processing Pipeline
↓
DB Persistence
↓
Publish
```

Publish 조건:

```text
CollectionRun.status = success
AND
분석 대상 Document failed_count = 0
```

## 3.5 개별 공고 재수집

```text
POST /api/admin/announcements/{id}/recollect
↓
pipeline_gateway.recollect_announcement()
↓
ANNOUNCEMENT_RECOLLECTOR
↓
integration_service.recollect_persist_and_process()
↓
collection_service.recollect_and_persist()
↓
새 Document 저장
↓
new_analysis_document_ids 처리
```

개별 재수집은 전체 Collection Publish를 자동 실행하지 않는다.

## 3.6 개별 Document 재처리

```text
POST /api/admin/documents/{document_id}/reprocess
↓
pipeline_gateway.reprocess_document()
↓
DOCUMENT_REPROCESSOR
↓
pipeline.document_processor:reprocess_document
```

실제 처리:

```text
Document DB context
↓
storage_path의 원본 파일
↓
Format Detection
↓
Parser
↓
Normalizer
↓
Structure / Verification
↓
Chunking
↓
Embedding
↓
persist_document_outputs()
↓
KeyInformation 추출 및 저장
↓
activate_processing_run()
```

---

# 4. 다른 파트와의 연결 관계

Docker 분리 준비에서 가장 중요한 부분이다.

현재 연결이 **HTTP / Python import / DB / File / subprocess** 중 무엇인지 구분한다.

| 호출 주체 | 대상 | 현재 연결 방식 | 현재 구현 | Docker 분리 시 확인 |
|---|---|---|---|---|
| User Frontend | Backend | **HTTP** | `/api/*` | 유지 가능 |
| Admin Frontend | Backend | **HTTP** | `/api/admin/*` | 유지 가능 |
| Backend | RAG | **Python import / importlib** | `rag.service:answer_question` | Backend → RAG HTTP 계약 필요 |
| Backend | Integration Service | **Python import / importlib** | `COLLECTION_RUNNER` | Worker 분리 경계 재설계 |
| Backend | Document Processor | **Python import / importlib** | `pipeline.document_processor:reprocess_document` | Backend → Document Worker 통신 필요 |
| Collection Service | Crawler | **Python import** | `crawler.crawler.crawl_lh_notices()` | Worker 내부/별도 경계 결정 |
| Backend | PostgreSQL | **DB** | SQLAlchemy + psycopg | `postgres` service name으로 변경 |
| RAG | PostgreSQL/pgvector | **DB** | SQLAlchemy 직접 조회 | RAG Container → postgres |
| RAG | Embedding | **Python import + GPU** | BGE-M3 직접 로드 | Embedding Service 호출로 변경 |
| RAG | llama.cpp | **HTTP** | OpenAI compatible API | `llm:8080` 등으로 변경 |
| Document Processor | 원본 HWP/HWPX | **File** | `Document.storage_path` | 공유 Volume 필수 |
| Document Processor | Parser/Normalizer/Structure/Chunking | **subprocess / File** | 단계별 Python 실행 | Worker 내부 유지 가능 |
| Document Processor | Embedding | **subprocess + GPU** | `run_embeddings.py` | Embedding Service 호출로 변경 |
| Document Processor | PostgreSQL | **DB** | Persistence Service | Worker DB 접근 정책 결정 |
| Backend/RAG/Pipeline | ErrorLog | **Python import + DB** | `record_error()` | 서비스 분리 시 경계 결정 |

## 4.1 현재 확실한 HTTP 경계

```text
Frontend → Backend
RAG → llama.cpp
```

현재 llama.cpp:

```text
http://127.0.0.1:8080
```

Docker 목표 예:

```text
http://llm:8080
```

## 4.2 Python import / callable 경계

현재 Docker 분리에서 가장 주의해야 하는 영역:

```text
Backend → RAG
Backend → Pipeline
Collection Service → Crawler
Document Processor → Backend Persistence
RAG → Embedding
```

현재 `.env.example`:

```env
RAG_ANSWER_FUNCTION=rag.service:answer_question
COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
ANNOUNCEMENT_RECOLLECTOR=backend.app.services.integration_service:recollect_persist_and_process
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document
```

이 값은 다른 Container의 Python 함수를 호출할 수 있는 네트워크 주소가 아니다.

Container가 분리되면 HTTP API 또는 Worker/Queue 계약으로 변경해야 한다.

## 4.3 DB 연결

현재:

```text
Backend → SQLAlchemy → PostgreSQL
RAG → SQLAlchemy → PostgreSQL + pgvector
```

Docker 목표 예:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

## 4.4 File 연결

DB:

```text
documents.storage_path
```

Document Processor는 이 경로에서 실제 파일을 찾는다.

Docker 분리 시 반드시 같은 파일을 Worker Container가 볼 수 있도록 공유 Volume 정책이 필요하다.

---

# 5. 주요 파일 구조와 역할

## 5.1 Backend Entry / Router

```text
backend/app/main.py
backend/app/api/router.py
backend/app/api/routes/
```

현재 Route:

```text
health.py
announcements.py
chat.py
admin.py
admin_auth.py
glossary.py
```

## 5.2 Schema

```text
backend/app/schemas/
```

Frontend ↔ Backend Request / Response 계약의 기준이다.

## 5.3 사용자 Service

```text
backend/app/services/announcement_service.py
backend/app/services/chat_service.py
backend/app/services/glossary_service.py
```

## 5.4 관리자 Service

```text
backend/app/services/admin_service.py
backend/app/services/admin_auth_service.py
```

## 5.5 Collection / Integration

```text
backend/app/services/collection_service.py
backend/app/services/integration_service.py
backend/app/services/collection_publish_service.py
backend/app/services/document_role_service.py
```

## 5.6 Pipeline Gateway / Persistence

```text
backend/app/services/pipeline_gateway.py
backend/app/services/pipeline_persistence.py
backend/app/services/key_information_service.py
```

## 5.7 Error

```text
backend/app/services/error_log_service.py
```

## 5.8 DB

```text
backend/app/db/
backend/app/models/
migrations/
alembic.ini
```

## 5.9 Document Processor

```text
pipeline/document_processor.py
```

## 5.10 RAG

```text
rag/service.py
rag/db_pipeline.py
rag/retrieval/hybrid_search.py
rag/generation/generator.py
rag/generation/llm_client.py
```

---

# 6. 주요 함수 및 실제 호출 순서

## 6.1 공고 목록

```text
GET /api/announcements
↓
get_announcements()
↓
list_active_announcements()
↓
PostgreSQL
```

## 6.2 공고 상세

```text
GET /api/announcements/{announcement_id}
↓
get_announcement()
↓
get_active_announcement()
↓
Announcement + Documents + KeyInformation
```

## 6.3 Chat

```text
POST /api/chat
↓
chat()
↓
answer_question_via_rag()
↓
_load_answer_question()
↓
rag.service:answer_question
↓
DBRAGPipeline.ask()
↓
hybrid_search()
↓
Vector + Keyword + RRF
↓
generate_answer()
↓
call_llama_cpp_chat()
↓
ChatResponse
```

## 6.4 전체 수집

```text
POST /api/admin/announcements/collect
↓
run_collection()
↓
collect_announcements()
↓
collect_persist_and_process()
↓
collect_and_persist()
↓
crawl_lh_notices()
↓
persist_collection_result()
↓
process_document_ids()
↓
reprocess_document()
↓
publish_collection_run()
```

## 6.5 Document 처리

```text
reprocess_document(document_id)
↓
process_document(document_id)
↓
get_registered_document_context()
↓
Parser
↓
Normalizer
↓
Structure / Verification
↓
Chunking
↓
Embedding
↓
persist_document_outputs()
↓
extract_key_information()
↓
upsert_key_information()
↓
activate_processing_run()
```

---

# 7. 데이터 흐름

## 7.1 Collection

```text
Crawler Result
↓
persist_collection_result()
↓
collection_runs
↓
announcements
↓
documents
```

## 7.2 Document Processing

입력:

```text
document_id
```

DB context:

```text
announcement_key
announcement_db_id
document_db_id
original_filename
document_format
storage_path
```

Pipeline 산출:

```text
Parsed JSON
Normalized JSON
Structure JSON
Verification JSON
Chunks JSON
Embedding metadata
Embedding vectors
KeyInformation
```

DB 저장:

```text
processing_runs
document_structures
chunk_sets
chunks
embeddings
key_information
```

## 7.3 RAG

입력:

```text
announcement_id
question
```

검색 범위:

```text
Active Collection
+ 요청 announcement_id
+ active ProcessingRun
+ active ChunkSet
+ completed Chunk
+ completed Embedding
```

Retrieval:

```text
Question
↓
BGE-M3 Query Embedding
↓
Vector Search
+
Keyword Search
↓
RRF
↓
Top Hybrid Results
```

Generation:

```text
검색 결과
↓
Context
↓
Prompt
↓
llama.cpp
↓
answer + evidence
```

---

# 8. DB / API / 외부 서비스 연결

## 8.1 주요 DB 관계

```text
CollectionRun
    ↓
Announcement
    ↓
Document
    ↓
ProcessingRun
    ├→ DocumentStructure
    └→ ChunkSet
          ↓
         Chunk
          ↓
       Embedding

Announcement
    ↓
KeyInformation

SystemState
    ↓
active_collection_run_id

ErrorLog
→ CollectionRun / Announcement / Document / ProcessingRun 선택 연결

Glossary
→ Collection과 독립
```

## 8.2 Document Role

```text
primary
supporting
unknown
```

### 전체 수집 자동 처리 기준

| Role | DB 저장 | 자동 Processing | KeyInformation | RAG 서비스 대상 |
|---|---:|---:|---:|---:|
| primary | O | O | O | O |
| supporting | O | X | X | X |
| unknown | O | X | X | X |

전체 수집에서 자동 분석 대상으로 전달되는 조건:

```text
document_role = primary
AND
download_status = completed
```

`unknown`이 남아 있으면 Collection Publish 검증이 실패한다.

> **주의:** 위 표는 전체 수집의 자동 처리 정책이다. 현재 관리자
> `POST /api/admin/documents/{document_id}/reprocess`와
> `pipeline.document_processor.reprocess_document()` 자체에는
> `document_role == primary`를 강제하는 검증이 없다. 따라서 관리자가
> supporting/unknown Document ID를 직접 재처리하는 경로까지 시스템적으로
> 차단되어 있다고 해석하면 안 된다.

## 8.3 pgvector

현재 기대 조건:

```text
model_name 일치
dimension = 1024
normalized = true
status = completed
embedding IS NOT NULL
```

## 8.4 llama.cpp

```text
POST /v1/chat/completions
```

현재:

```env
LLAMA_BASE_URL=http://127.0.0.1:8080
LLAMA_MODEL=gemma
```

Docker 목표 예:

```env
LLAMA_BASE_URL=http://llm:8080
```

## 8.5 Embedding

현재:

```text
RAG → BGE-M3 직접 로드
Document Processor → run_embeddings.py → BGE-M3 직접 로드
```

Docker 목표:

```text
RAG ─┐
     ├→ Embedding Service
Worker ┘
```

---

# 9. 실행 방법 및 환경변수

## 9.1 AWS Runtime 경로 확인

기존 AWS 작업 기록에서 다음 경로를 사용한 이력이 있다.

```text
프로젝트 예시:
/home/ubuntu/ddokbot/one-cycle

Python 가상환경 예시:
/home/ubuntu/ddokbot/venvs/one-cycle-backend
```

하지만 GitHub `develop` 코드만으로 **현재 AWS 서버가 지금도 위 절대경로를
사용한다고 확정할 수는 없다.**

실행 전에 서버에서 다음을 먼저 확인한다.

```bash
pwd
git remote -v
git branch --show-current
git log -1 --oneline
which python
python --version
```

## 9.2 Backend

2026-08-26 AWS Runtime 검증에서는 FastAPI를 `18000` Port에서 확인했다.

Repository Root와 사용할 Python을 확인한 뒤 실행한다.

```bash
cd <PROJECT_ROOT>

export PYTHONPATH=.

python -m uvicorn backend.app.main:app \
  --host 127.0.0.1 \
  --port 18000
```

특정 Virtualenv의 Python을 사용할 경우 `python` 대신
`which python`으로 확인한 Interpreter 경로를 사용한다.

Health:

```bash
curl -i http://127.0.0.1:18000/api/health
curl -i http://127.0.0.1:18000/api/health/db
```

## 9.3 PostgreSQL

현재 PostgreSQL + pgvector는 Docker로 운영한다.

```text
pgvector/pgvector:0.8.2-pg16
```

현재 `.env.example`:

```env
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=one_cycle
POSTGRES_USER=one_cycle
POSTGRES_PASSWORD=CHANGE_ME
```

Docker 분리 후 예:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

## 9.4 주요 callable

```env
RAG_ANSWER_FUNCTION=rag.service:answer_question
COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
ANNOUNCEMENT_RECOLLECTOR=backend.app.services.integration_service:recollect_persist_and_process
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document
```

`ERROR_RETRY_RUNNER`는 현재 연결되지 않았다.

---

# 10. 테스트 방법

## 10.1 핵심 관련 테스트

```text
tests/backend/test_evaluation_services.py
tests/backend/test_integration_service.py
tests/backend/test_collection_publish_service.py
```

2026-08-27 평가 DB Backend 작업 당시 확인한 결과:

```text
18 passed
```

## 10.2 Backend 전체

같은 작업 시점의 전체 Backend 테스트 기록:

```text
71 passed
4 failed
```

4개 실패는 당시 기존 `KeyInformationExtractor` 테스트다.

> 이 숫자는 해당 작업 시점의 테스트 실행 기록이다. 현재
> `develop@1c3b2e9`에서 전체 테스트를 다시 실행한 결과라고 확대 해석하지 않는다.
> 현재 HEAD의 최종 테스트 상태가 필요하면 해당 Commit에서 pytest를 재실행한다.

## 10.3 AWS Runtime

`docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md` 기준이며,
아래 수치는 **2026-08-26 `develop@476575c`에서 확인한 Runtime 기록**이다.
현재 문서 기준 `develop@1c3b2e9` 전체 기능의 재검증 결과를 의미하지 않는다.

```text
CollectionRun: 2
Announcement: 50
Document: 86
primary: 48
supporting: 38
unknown: 0

Processing requested: 48
success: 48
failed: 0

Chunk: 13,863
Embedding: 13,863

dimension: 1024
normalized: true

자동 Publish: PASS
User Announcement API: PASS
```

---

# 11. 주요 트러블슈팅

## 11.1 AWS OOM / 메모리 부족

Backend, RAG, Embedding, LLM 등이 같은 AWS EC2의 RAM/GPU를 공유한다.

Docker 분리 후에도 물리 자원은 증가하지 않는다.

## 11.2 Local Windows CUDA 불가

평가 문서 Pipeline에서:

```text
EMBEDDING_FAILED
CUDA를 사용할 수 없습니다.
```

Local에서는 Parser → Normalizer → Structure → Verification → Chunking까지 정상 확인했고 Embedding 이후는 AWS GPU 환경이 필요했다.

## 11.3 PostgreSQL Volume

DB 데이터는 Container 삭제와 별개로 Persistent Volume에 유지되어야 한다.

Volume을 임의 삭제하면 안 된다.

## 11.4 Publish 조건

새 전체 Collection은 Publish되어야 사용자 서비스에 노출된다.

현재 active Collection의 기존 Document 재처리는 새 ProcessingRun / ChunkSet activation이 핵심이며 Collection Publish를 다시 할 필요는 없다.

## 11.5 Document Role

파일명 분류가 `primary / supporting / unknown` 처리 정책에 직접 영향을 준다.

## 11.6 실패한 재처리 보호

새 처리 실패 시 기존 active ProcessingRun / ChunkSet / KeyInformation을 보호해야 한다.

## 11.7 Backend ↔ RAG / Pipeline 직접 import

Container만 먼저 분리하고 Python callable 계약을 그대로 두면 동작하지 않는다.

## 11.8 원본 파일 경로

Document Processor는 `storage_path`가 실제 파일을 가리킨다고 가정한다.

Docker 분리 시 공유 Volume과 경로 정책이 필요하다.

---

# 12. 현재 구조에서 알아야 할 사항

## 12.1 완전한 Microservice 구조가 아니다

```text
Backend
RAG
Crawler
Pipeline
Embedding
```

이 한 Repository 안에서 Python import로 강하게 연결되어 있다.

## 12.2 Backend는 아직 API 전용이 아니다

Docker 목표:

```text
Backend = API 처리
```

현재:

```text
Backend API
→ Python callable
→ Crawler / Pipeline 실행
```

## 12.3 RAG도 아직 별도 HTTP Service가 아니다

현재:

```text
chat_service
→ importlib
→ rag.service
```

Docker 목표:

```text
Backend
→ HTTP
→ RAG Container
```

## 12.4 Embedding Service도 아직 없다

현재 RAG와 Document Processor가 각각 BGE-M3를 직접 사용한다.

## 12.5 llama.cpp는 이미 HTTP 경계가 있다

따라서 Docker 분리 시 Hostname 전환이 중심이다.

## 12.6 사용자 원본 파일 URL

Admin 다운로드 API는 있지만 사용자 상세 API에는 파일 URL이 없다.

사용자용 파일 Endpoint / `documents[].downloadUrl` 같은 계약이 추가로 필요하다.

## 12.7 평가 DB

```text
운영: one_cycle
평가: one_cycle_evaluation_tmp
```

Docker 환경에서도 반드시 구분한다.

---

# 13. Docker 분리 전 확인할 부분

AWS Docker 운영안의 목표 서비스:

```text
nginx
backend
rag
document-worker
embedding
llm
postgres
```

Queue는 현재 제외하고 후속 확장 대상으로 본다.

## 13.1 현재 AS-IS

```text
Frontend
↓ HTTP
Backend FastAPI
├→ Python import → RAG
├→ Python import → Integration / Crawler
├→ Python import → Document Processor
└→ DB → PostgreSQL

RAG
├→ Python import → BGE-M3
├→ DB → PostgreSQL + pgvector
└→ HTTP → llama.cpp

Document Processor
├→ File → HWP/HWPX
├→ subprocess → Parser
├→ subprocess → Normalizer
├→ subprocess → Structure
├→ subprocess → Chunking
├→ subprocess → Embedding/BGE-M3
└→ Python import / DB → Persistence
```

## 13.2 Docker 목표 TO-BE

```text
User / Admin
↓
Nginx
↓
Backend
├→ RAG
├→ Document Worker
└→ PostgreSQL

RAG
├→ Embedding Service
├→ PostgreSQL
└→ LLM Service

Document Worker
├→ Embedding Service
└→ PostgreSQL
```

## 13.3 Backend → RAG

현재:

```text
Python import
rag.service:answer_question
```

Docker 분리 전 결정:

```text
RAG HTTP Endpoint
Request Schema
Response Schema
Timeout
Error 처리
Health Check
```

## 13.4 Backend → Document Worker

현재:

```text
Python callable
```

Docker 분리 전 결정:

```text
동기 HTTP
비동기 Worker
향후 Queue
작업 ID
상태 조회
ErrorLog 주체
```

현재 Queue는 도입하지 않는다.

## 13.5 Embedding API

신규 계약이 필요하다.

최소 구분:

```text
문서 Chunk Embedding
질문 Query Embedding
```

중요 값:

```text
BAAI/bge-m3
dimension = 1024
normalized = true
```

## 13.6 File Volume

Docker 운영안 예시 프로젝트 경로:

```text
/home/ubuntu/ddokbot/one-cycle_development
```

기존 AWS 작업 기록에서 사용한 프로젝트 Root 예:

```text
/home/ubuntu/ddokbot/one-cycle
```

Docker 운영안의 예시 경로와 기존 작업 기록의 경로가 다르며,
GitHub 코드만으로 현재 서버의 실제 Root를 확정할 수 없다.

**Compose 작성 전에 AWS에서 `pwd`, Git Branch/Commit을 직접 확인하고
실제로 사용할 Root를 확정해야 한다.**

확인 항목:

```text
원본 문서 Host 저장 위치
Container 내부 공통 경로
DB storage_path 정책
개발 Volume Mount
운영 Volume
```

## 13.7 PostgreSQL

현재 이미 Docker로 운영 중이다.

확인:

```text
Named Volume 유지/Bind Mount 전환
POSTGRES_HOST
Container Network
Health Check
Migration 실행 주체
Backup
```

## 13.8 GPU

AWS NVIDIA L4를 사용한다.

초기 GPU 대상 목표:

```text
embedding
llm
```

BGE-M3 중복 로딩을 줄이는 것이 Embedding Service 분리 목적 중 하나다.

## 13.9 Port / Hostname

운영안에서 비교적 일관된 목표 값:

```text
postgres:5432
llm:8080
backend:18000
```

RAG / Embedding Port는 운영안 문서 안에서 예시가 서로 다르다.

```text
예시 A
embedding:8001
rag:8002

예시 B
embedding:18002
rag:18001
```

따라서 현재 인수인계 기준으로 다음 값은 **미확정**이다.

```text
RAG internal port
Embedding internal port
```

최종 Source of Truth는 실제 구현될 `infra/docker-compose.yml`로 통일한다.

## 13.10 Nginx

배포 시:

```text
Internet
↓ HTTPS 443
Nginx
↓
Backend
```

개발 단계에서는 필수 실행 대상으로 보지 않는다.

---

# 14. Source of Truth

| 영역 | 최종 기준 |
|---|---|
| FastAPI App | `backend/app/main.py` |
| Router 등록 | `backend/app/api/router.py` |
| 사용자 Announcement | `backend/app/api/routes/announcements.py`, `backend/app/services/announcement_service.py` |
| Chat | `backend/app/api/routes/chat.py`, `backend/app/services/chat_service.py` |
| Admin API | `backend/app/api/routes/admin.py` |
| Glossary | `backend/app/api/routes/glossary.py` |
| Collection | `backend/app/services/collection_service.py` |
| Integration | `backend/app/services/integration_service.py` |
| Gateway | `backend/app/services/pipeline_gateway.py` |
| Persistence | `backend/app/services/pipeline_persistence.py` |
| Publish | `backend/app/services/collection_publish_service.py` |
| Document Role | `backend/app/services/document_role_service.py` |
| ErrorLog | `backend/app/services/error_log_service.py` |
| ORM | `backend/app/models/` |
| RAG Entry | `rag/service.py` |
| RAG DB / Vector Search | `rag/db_pipeline.py` |
| Hybrid Search | `rag/retrieval/hybrid_search.py` |
| Generation | `rag/generation/generator.py` |
| llama.cpp Client | `rag/generation/llm_client.py` |
| Document Processor | `pipeline/document_processor.py` |
| Migration | `migrations/versions/` |
| 환경변수 Template | `.env.example` |
| Docker | `infra/docker-compose.yml`, `infra/` |

---

# 15. 최종적으로 확인할 Backend / DB 문서

Backend / DB 인수인계 시:

```text
1. docs/BACKEND.md
2. docs/API.md
3. docs/DATABASE.md
4. docs/ENVIRONMENT.md
5. docs/BACKEND_INTEGRATION.md
```

필요할 때 참고:

```text
docs/BACKEND_DB_EVALUATION_WORKFLOW.md
docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md
docs/BACKEND_DB_INTEGRATION_HISTORY.md
```

---

# 16. Git / 운영 원칙

```text
Windows Local
→ 코드/문서 수정
→ 테스트
→ commit
→ push
→ PR
→ develop merge
```

AWS:

```text
origin/develop pull
→ Runtime 실행 / 검증
```

AWS 서버를 코드 작성 / commit / push 기준 저장소로 사용하지 않는다.

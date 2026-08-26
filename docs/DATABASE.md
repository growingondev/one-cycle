# Database Architecture

> 기준 시점: **2026-08-26**
> Stack: PostgreSQL 16 + pgvector + SQLAlchemy + Alembic
> 목적: One-Cycle의 현재 DB 구조, Persistence, Active Dataset, Runtime RAG 연결을 설명한다.

---

# 1. Database Stack

```text
PostgreSQL
+ pgvector
+ SQLAlchemy
+ Alembic
```

역할:

```text
PostgreSQL  → Application / 운영 데이터
pgvector    → Embedding vector 및 cosine similarity
SQLAlchemy  → ORM / Session
Alembic     → Schema migration
```

AWS에서는 PostgreSQL + pgvector를 Docker로 실행한다.

---

# 2. 주요 DB 코드

```text
backend/app/db/
backend/app/models/
backend/app/services/collection_service.py
backend/app/services/pipeline_persistence.py
backend/app/services/key_information_service.py
backend/app/services/collection_publish_service.py
backend/app/services/error_log_service.py

migrations/
alembic.ini

infra/docker-compose.yml
infra/postgres/init/01-enable-vector.sql
```

---

# 3. 주요 Model

```text
Admin
CollectionRun
Announcement
Document
ProcessingRun
ProcessingArtifact
DocumentStructure
ChunkSet
Chunk
Embedding
KeyInformation
ErrorLog
Glossary
SystemState
```

실제 column / constraint / FK의 최종 기준은 ORM Model과 Alembic migration이다.

## Glossary

용어 사전은 다른 Collection 데이터와 독립된 운영 테이블이다.

```text
glossary
├─ id PK
├─ term VARCHAR(200) NOT NULL UNIQUE
├─ definition TEXT NOT NULL
├─ category VARCHAR(100) NOT NULL
├─ is_active BOOLEAN NOT NULL DEFAULT true
├─ created_at
└─ updated_at
```

초기 Seed는 40개이며 `term` 기준 중복 없이 재실행 가능하도록 관리한다.

---

# 4. 핵심 데이터 관계

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
```

`Chunk`는 RAG 검색 범위 제한을 단순하게 하기 위해 `announcement_id`와 `document_id`도 직접 가진다.

---

# 5. CollectionRun

수집 한 번을 하나의 snapshot/run으로 저장한다.

대표 상태:

```text
running
success
partial
failed
```

대표 count:

```text
total_announcement_count
successful_announcement_count
failed_announcement_count
```

중요:

현재 `CollectionRun`에는 다음 column이 없다.

```text
is_published
published_at
```

서비스 공개 상태는 `SystemState.active_collection_run_id`로 관리한다.

---

# 6. Announcement

LH 공고 한 건.

같은 LH 공고라도 서로 다른 CollectionRun에 속하면 서로 다른 수집 snapshot으로 존재할 수 있다.

사용자 API는 모든 Announcement가 아니라 **Active Collection**에 속한 Announcement를 조회한다.

---

# 7. Document

Announcement 첨부 HWP/HWPX 문서.

주요 개념:

```text
original_filename
document_format
storage_path
download_status
document_role
```

현재 `document_role`:

```text
primary
supporting
unknown
```

모든 HWP/HWPX Document를 DB에 저장하지만,
현재 AI 전체 처리 대상은 `primary + download completed`다.

---

# 8. ProcessingRun

Document 한 번의 처리 실행 결과.

같은 Document를 재처리해도 기존 결과를 덮어쓰지 않고 새 ProcessingRun을 만들 수 있다.

```text
Document
├→ ProcessingRun A (old / inactive)
└→ ProcessingRun B (new / active)
```

대표 정상 조건:

```text
execution_status = succeeded
verification_status = pass
is_active = true
```

## Timestamp 주의

현재 ProcessingRun은 실제 Parser 시작 시점이 아니라 Persistence 단계에서 만들어진다.

따라서 `started_at`, `finished_at`은 전체 Pipeline wall-clock 시간으로 해석하면 안 된다.

실제 document 87 재처리에서도 DB timestamp와 실제 처리 시간이 동일한 의미가 아님을 확인했다.

---

# 9. DocumentStructure

특정 ProcessingRun의 구조화 결과를 저장한다.

```text
ProcessingRun
→ DocumentStructure
```

문서 처리 알고리즘이 ORM에 직접 임의 INSERT하는 것이 아니라,
Pipeline 산출물을 Backend Persistence가 검증해 저장한다.

---

# 10. ChunkSet

특정 ProcessingRun의 Chunk 결과 묶음.

```text
ProcessingRun
→ ChunkSet
→ Chunk N
```

`ChunkSet`은 Chunking 전략 그 자체가 아니라 **특정 Chunking 실행 결과의 버전 단위**다.

대표 상태:

```text
status = completed
is_active = true
chunk_count = 실제 Chunk 수
```

---

# 11. Chunk

RAG 검색 실제 단위.

주요 성격:

```text
external_chunk_key
chunk_index
announcement_id
document_id
document_format
content_type
section_path
title
content
search_text
embedding_text
source_reference
metadata
status
```

`chunks.id`는 DB 내부 PK,
`external_chunk_key`는 Pipeline/RAG 추적용 key다.

---

# 12. Embedding

각 Chunk에 대응하는 pgvector Vector.

현재 검증 기준:

```text
model      BAAI/bge-m3
dimension  1024
normalized true
status     completed
```

Publish 시 primary Document의 모든 Chunk에 정상 Embedding이 있는지 확인한다.

---

# 13. KeyInformation

Announcement 상세 화면용 구조화 핵심정보.

대표 필드:

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

용도는 RAG와 다르다.

```text
KeyInformation
→ 사용자 핵심정보 카드

Chunk + Embedding
→ RAG Retrieval
```

현재 문서 처리에서 실제 추출 / 저장까지 연결되어 있다.

KeyInformation은 Structure / Verification 결과를 입력으로 사용한다.

---

# 14. ErrorLog

Crawler / Pipeline / RAG / LLM 운영 오류를 공통 형태로 저장한다.

공통 진입점:

```python
record_error(...)
```

반환:

```text
error_id
```

관련 ID가 일부만 전달되면 DB 관계를 통해 상위 연결을 검증 / 보완한다.

---

# 15. SystemState / Active Collection

Singleton 상태의 핵심 값:

```text
active_collection_run_id
```

의미:

```text
수집 성공
≠
서비스 공개 완료
```

새 Collection이 문서 처리 / Embedding / 검증을 통과한 뒤 Publish되어야 사용자 서비스 대상이 된다.

현재 전체 신규 수집 경로에서는 Integration Service가 `CollectionRun.status = success`이고 `analysis_document_ids` 처리 결과의 `failed_count = 0`일 때 `publish_collection_run(collection_run_id)`을 자동 호출한다.

실제 Publish validation과 `SystemState.active_collection_run_id` 전환은 `collection_publish_service.py`가 담당한다.

개별 공고 재수집은 자동 Publish하지 않는다.

---

# 16. Persistence 실제 순서

현재 Document Processor의 전체 실행:

```text
Parser
→ Normalizer
→ Structure + Verification
→ Chunking
→ Embedding
→ persist_document_outputs()
```

`persist_document_outputs()` 저장 대상:

```text
ProcessingRun
DocumentStructure
ChunkSet
Chunk
Embedding
```

그 다음:

```text
Structure / Verification 기반 KeyInformation 추출
→ KeyInformation upsert
→ activate_processing_run()
```

## 논리적 의존성

```text
Structure + Verification
├→ KeyInformation
└→ Chunking → Embedding
```

KeyInformation이 물리적으로 Embedding 뒤에 저장되는 것은
현재 ProcessingRun ID를 먼저 확보하기 위한 실행 순서 때문이다.

---

# 17. Activation

새 결과를 바로 서비스 데이터로 만들지 않는다.

```text
새 ProcessingRun
→ Persistence
→ 검증
→ KeyInformation
→ Activation
```

Activation 시:

```text
기존 active ProcessingRun → false
신규 ProcessingRun        → true

기존 active ChunkSet      → false
신규 ChunkSet             → true
```

새 결과 실패 시 기존 정상 데이터를 유지한다.

---

# 18. Collection Publish

`publish_collection_run(id)`는:

```text
Collection validation
→ SystemState row lock
→ active_collection_run_id 변경
```

을 수행한다.

Publish는 CollectionRun에 별도 `published` flag를 기록하는 방식이 아니다.

Primary 검증:

```text
download completed
active ProcessingRun
succeeded
verification pass
active completed ChunkSet
Chunk count 정합성
모든 Chunk completed
모든 Chunk에 정상 BGE-M3 Embedding
dimension 1024
normalized true
```

Supporting은 현재 처리 validation을 하지 않는다.

Unknown Document가 존재하면 Publish를 막는다.

HWP/HWPX primary가 없는 공고는 metadata-only로 Publish 허용될 수 있다.

---

# 19. Runtime RAG DB Join

현재 `rag/db_pipeline.py`는 개념적으로:

```text
SystemState
→ Active CollectionRun
→ Announcement
→ Chunk
→ ChunkSet(active)
→ ProcessingRun(active)
→ Embedding
```

을 사용한다.

필터:

```text
요청 announcement_id
Chunk.status = completed
ChunkSet.is_active = true
ProcessingRun.is_active = true
Embedding.status = completed
Embedding.model_name = 현재 query model
Embedding.dimension = 1024
Embedding.normalized = true
Embedding.embedding IS NOT NULL
```

pgvector cosine distance:

```sql
embedding <=> query_vector
```

Similarity:

```text
1 - cosine distance
```

---

# 20. AWS 실제 데이터 검증

> 최신 AWS Runtime 검증(2026-08-26): `docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md`

2026-08-25 실제 LH 수집:

```text
Announcement  50
Document      88
primary       48
supporting    40
unknown        0
```

Primary 처리:

```text
48 / 48 succeeded
```

검색 데이터:

```text
Chunk       14,047
Embedding   14,047
```

Publish:

```text
CollectionRun id = 1
SystemState.active_collection_run_id = 1
```

단일 재처리 검증:

```text
document_id = 87

old ProcessingRun id=48
→ is_active=false

new ProcessingRun id=49
→ succeeded
→ verification=pass
→ is_active=true
```

---

# 21. Alembic

현재 로컬 확인:

```text
alembic heads
→ 3d70b82ff082 (head)
```

현재 단일 head다.

Schema 변경 시 원칙:

```text
Model 변경
→ Migration 작성
→ alembic heads 확인
→ migration review
→ upgrade 테스트
→ 코드 / 테스트 / 문서와 함께 PR
```

이번 `제출서류` Document Role keyword 수정은 **Schema 변경이 아니므로 Migration이 필요 없다.**

---

# 22. DB 상태 확인 기준

DB 연결:

```sql
SELECT 1;
```

Active Collection:

```sql
SELECT active_collection_run_id
FROM system_state
WHERE id = 1;
```

RAG 검색 문제 시 순서:

```text
1. Active Collection인가
2. 요청 Announcement가 해당 Collection에 속하는가
3. primary Document가 정상 처리됐는가
4. active ProcessingRun인가
5. active ChunkSet인가
6. Chunk completed인가
7. Embedding completed인가
8. model / dimension / normalized가 맞는가
```

---

# 23. Runtime 서비스 포트

AWS 기준:

| Service | Port |
|---|---:|
| PostgreSQL | 5432 |
| FastAPI | 18000 |
| llama.cpp | 8080 |
| User Vite | 5173 |
| Admin Vite | 3000 |

---

# 24. Source of Truth

| 영역 | 기준 |
|---|---|
| DB Session | `backend/app/db/session.py` |
| ORM | `backend/app/models/` |
| Collection Persistence | `backend/app/services/collection_service.py` |
| Pipeline Persistence | `backend/app/services/pipeline_persistence.py` |
| KeyInformation | `backend/app/services/key_information_service.py` |
| Publish | `backend/app/services/collection_publish_service.py` |
| Runtime Retrieval SQL | `rag/db_pipeline.py` |
| Migration | `migrations/versions/` |
| Infra | `infra/docker-compose.yml` |

---

# 25. 핵심 원칙

```text
1. DB Write와 Activation은 다른 단계다.

2. ProcessingRun / ChunkSet은 재처리 버전과
   안전한 서비스 전환을 위한 구조다.

3. Collection Publish는 SystemState의
   active_collection_run_id 전환이다.

4. Runtime RAG는 Active Collection +
   active ProcessingRun + active ChunkSet +
   정상 Embedding을 검색한다.

5. ORM을 변경하면 Migration이 필요하지만,
   단순 분류 keyword 변경에는 Migration이 필요 없다.
```

# DDOKBOT Database 인수인계 가이드

> 기준 시점: **2026-08-27**
>
> 기준 브랜치: `develop`
>
> 기준 커밋: `1c3b2e9`
>
> Stack: PostgreSQL 16 + pgvector + SQLAlchemy + psycopg + Alembic
>
> 목적: DB를 처음 보는 개발자가 어떤 데이터가 어디 저장되고, 누가 저장·조회하며, RAG와 Backend가 어떻게 같은 DB를 사용하는지 이해하고 Docker 분리까지 이어갈 수 있도록 한다.
>
> 실제 Column / Constraint / FK의 최종 기준(Source of Truth)은 `backend/app/models/`와 `migrations/versions/`다.

---

# 1. DB 파트 개요

현재 DB는 One-Cycle 서비스의 영구 데이터 저장소다.

저장 대상:

```text
수집 실행 정보
공고
원본 문서 메타데이터
문서 처리 실행 이력
구조화 결과
Chunk
Embedding Vector
핵심정보
서비스 Active Collection
오류
관리자
Glossary
```

DB는 단순한 CRUD 저장소가 아니라 다음 기능의 공통 상태를 연결한다.

```text
Crawler
Document Processing
Backend API
RAG Retrieval
Admin
User Frontend
```

현재 Backend와 RAG는 **같은 PostgreSQL을 각각 직접 조회**한다.

---

# 2. Database Stack

```text
PostgreSQL 16
+ pgvector
+ SQLAlchemy
+ psycopg
+ Alembic
```

역할:

| 구성 | 역할 |
|---|---|
| PostgreSQL | 서비스 운영 데이터 영구 저장 |
| pgvector | Embedding Vector 저장 및 유사도 검색 |
| SQLAlchemy | ORM / Query / Session |
| psycopg | PostgreSQL Driver |
| Alembic | Schema Migration |

현재 SQLAlchemy Engine은 다음 코드에서 생성된다.

```text
backend/app/db/session.py
```

연결 변수:

```text
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
```

현재 Engine:

```text
postgresql+psycopg
```

---

# 3. 현재 PostgreSQL 실행 구조

현재 PostgreSQL + pgvector는 이미 Docker Container로 운영한다.

```text
infra/docker-compose.yml
```

현재 Compose의 DB Service:

```text
service name: postgres
container_name: one-cycle-postgres
image: pgvector/pgvector:0.8.2-pg16
```

현재 Host Port Binding:

```text
127.0.0.1:${POSTGRES_PORT:-5432}:5432
```

즉 현재 Host Process 기준 DB 접속은 일반적으로:

```text
127.0.0.1:5432
```

이다.

DB Persistent Volume:

```text
postgres_data
→ /var/lib/postgresql/data
```

실제 Named Volume 이름:

```text
one-cycle-postgres-data
```

초기화 SQL:

```text
infra/postgres/init/01-enable-vector.sql
```

내용:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

# 4. Docker 운영안과 현재 DB 구조 차이

첨부된 AWS Docker 운영안에서는 향후 Backend / RAG / Document Worker도 Container로 분리한다.

현재:

```text
Host Backend ─┐
Host RAG ──────┼→ 127.0.0.1:5432
Host Pipeline ─┘
                    ↓
              postgres Container
```

Docker 분리 목표:

```text
backend Container ─┐
rag Container ──────┼→ postgres:5432
document-worker ────┘
                         ↓
                   postgres Container
```

즉 DB 자체는 이미 Container이지만, **DB를 사용하는 나머지 Process들이 아직 Host에서 실행되고 있다는 점**이 중요하다.

Docker 분리 후에는 일반적으로:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

처럼 Compose Service Name을 사용한다.

---

# 5. 주요 DB 코드

```text
backend/app/db/
├── base.py
└── session.py

backend/app/models/

backend/app/services/
├── collection_service.py
├── pipeline_persistence.py
├── key_information_service.py
├── collection_publish_service.py
├── announcement_service.py
├── admin_service.py
├── error_log_service.py
├── glossary_service.py
├── evaluation_service.py
└── evaluation_pipeline_service.py

rag/db_pipeline.py
rag/retrieval/keyword_search.py

migrations/
├── env.py
└── versions/

infra/
├── docker-compose.yml
└── postgres/init/01-enable-vector.sql
```

---

# 6. ORM Model 목록

현재 `backend/app/models/__init__.py` 기준 Model:

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

이 문서에서는 서비스 흐름에 중요한 Model 중심으로 설명한다.

---

# 7. 전체 데이터 관계

```text
CollectionRun
    ↓ 1:N
Announcement
    ↓ 1:N
Document
    ↓ 1:N
ProcessingRun
    ├→ DocumentStructure
    ├→ ProcessingArtifact
    └→ ChunkSet
          ↓ 1:N
         Chunk
          ↓ 1:N
       Embedding

Announcement
    ↓
KeyInformation

SystemState
    ↓
active_collection_run_id
    ↓
CollectionRun

ErrorLog
→ CollectionRun / Announcement / Document / ProcessingRun 선택 연결

Glossary
→ 위 Collection 구조와 독립

Admin
→ 관리자 인증/관리 데이터
```

`Chunk`는 RAG 검색을 단순하게 하기 위해 ChunkSet 관계 외에도 Announcement / Document 식별 정보를 직접 가진다.

---

# 8. CollectionRun

의미:

```text
한 번의 전체 수집 실행 snapshot
```

같은 LH 공고라도 다음처럼 Collection이 다르면 서로 다른 snapshot으로 존재할 수 있다.

```text
CollectionRun 1
└→ Announcement A

CollectionRun 2
└→ Announcement A
```

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

저장 주체:

```text
backend/app/services/collection_service.py
persist_collection_result()
```

조회 주체:

```text
Admin Service
Collection Publish Service
SystemState / User Announcement Service
RAG 범위 제한
```

중요:

현재 `CollectionRun` 자체에 다음 Column을 두는 방식이 아니다.

```text
is_published
published_at
```

서비스 공개 여부는 `SystemState`로 관리한다.

---

# 9. Announcement

의미:

```text
특정 Collection snapshot에 속한 LH 공고 한 건
```

주요 데이터:

```text
source_announcement_id
title
detail_url
region
notice_type
announcement_date
publication_status
collection_run_id
```

저장:

```text
Crawler Result
↓
collection_service.persist_collection_result()
↓
announcements
```

사용자 조회:

```text
announcement_service
```

관리자 조회:

```text
admin_service
```

RAG:

```text
요청 announcement_id
+ Active Collection
```

주의:

```text
detail_url
```

은 LH 공고 상세 페이지 URL이다.

원본 HWP/HWPX 파일 다운로드 URL과 다른 개념이다.

---

# 10. Document

의미:

```text
Announcement에 연결된 HWP/HWPX 첨부 문서
```

주요 데이터:

```text
announcement_id
original_filename
document_format
document_role
storage_path
file_size_bytes
checksum_sha256
download_status
error_message
```

지원 형식:

```text
hwp
hwpx
```

현재 Role:

```text
primary
supporting
unknown
```

저장 주체:

```text
collection_service.persist_collection_result()
collection_service.recollect_and_persist()
evaluation_service
```

원본 파일과 DB를 연결하는 핵심 값:

```text
storage_path
```

Document Processor는 DB의 `storage_path`를 읽어 실제 HWP/HWPX 파일을 찾는다.

---

# 11. Document Role과 처리 대상

### 전체 수집 자동 처리 정책

| Role | DB 저장 | 자동 Processing | KeyInformation | RAG 서비스 대상 |
|---|---:|---:|---:|---:|
| primary | O | O | O | O |
| supporting | O | X | X | X |
| unknown | O | X | X | X |

전체 수집에서 Processing 대상으로 반환되는 조건:

```text
document_role == primary
AND
download_status == completed
```

`collection_service.persist_collection_result()`가 다음을 반환한다.

```text
analysis_document_ids
```

Integration Service가 이 ID 목록을 Document Processor에 전달한다.

> **주의:** 위 표는 전체 수집의 자동 처리 정책이다. 현재 관리자
> Document 재처리 Endpoint와 `reprocess_document()` 자체에는
> `document_role == primary` 강제 검증이 없다. 따라서 DB Schema 수준에서
> supporting/unknown 문서의 수동 재처리를 차단하는 구조는 아니다.

---

# 12. ProcessingRun

의미:

```text
Document 한 건에 대한 특정 시점의 Processing 실행 결과
```

재처리 시 기존 Row를 덮어쓰는 방식이 아니다.

```text
Document
├→ ProcessingRun A
│   is_active = false
└→ ProcessingRun B
    is_active = true
```

대표 정상 조건:

```text
execution_status = succeeded
verification_status = pass
is_active = true
```

새 Processing 결과는 처음에는 inactive로 저장되고, 모든 필수 단계가 성공한 후 활성화한다.

현재 물리적 처리:

```text
Parser
→ Normalizer
→ Structure / Verification
→ Chunking
→ Embedding
→ Persistence
→ KeyInformation
→ Activation
```

중요:

현재 `ProcessingRun.started_at / finished_at`은 Persistence 단계에서 생성되는 값이므로 전체 Parser부터의 정확한 wall-clock 성능 지표로 해석하면 안 된다.

---

# 13. DocumentStructure

의미:

```text
특정 ProcessingRun의 최종 구조화 문서
```

관계:

```text
ProcessingRun
→ DocumentStructure
```

저장 주체:

```text
backend/app/services/pipeline_persistence.py
```

주요 내용:

```text
schema_version
structure_json
element_count
content_hash
```

KeyInformation 추출의 원천 데이터도 Structure / Verification 쪽이다.

---

# 14. ProcessingArtifact

문서 처리 과정의 산출물 정보를 ProcessingRun과 연결하기 위한 Model이다.

실제 Processing pipeline의 핵심 RAG 데이터는:

```text
DocumentStructure
ChunkSet
Chunk
Embedding
```

이고, `ProcessingArtifact`는 처리 산출물 관리/추적을 위한 별도 Model로 이해하면 된다.

정확한 Column은 ORM Model을 최종 기준으로 확인한다.

---

# 15. ChunkSet

의미:

```text
특정 ProcessingRun에서 생성된 Chunk 묶음 / 버전 단위
```

Chunking 알고리즘 그 자체가 아니라 **Chunking 실행 결과 집합**이다.

관계:

```text
ProcessingRun
→ ChunkSet
→ Chunk N
```

주요 개념:

```text
chunker_version
strategy
chunking_config
input_content_version
status
chunk_count
is_active
```

대표 정상 상태:

```text
status = completed
is_active = true
```

재처리 성공 시 새 ProcessingRun의 ChunkSet이 active가 되고 기존 ChunkSet은 inactive가 된다.

---

# 16. Chunk

의미:

```text
RAG 검색의 기본 문서 단위
```

저장 주체:

```text
pipeline_persistence
```

생성 원천:

```text
pipeline/chunking
→ chunks.json
```

RAG 조회 주체:

```text
rag/db_pipeline.py
rag/retrieval/keyword_search.py
rag/retrieval/hybrid_search.py
```

RAG 검색은 현재 단순 Vector Search만 사용하는 구조가 아니다.

```text
Vector Search
+
Keyword Search
↓
RRF
```

로 결합한다.

---

# 17. Embedding

의미:

```text
Chunk의 BGE-M3 Vector
```

현재 ORM은 pgvector `Vector(1024)`를 사용한다.

중요 제약:

```text
dimension = 1024
```

completed 상태에서는 Vector가 반드시 존재해야 한다.

Unique 기준:

```text
chunk_id
+ model_name
+ model_version
```

현재 주요 값:

```text
model_name = BAAI/bge-m3
dimension = 1024
normalized = true
```

현재 Status:

```text
pending
running
completed
failed
```

저장:

```text
Document Processor
↓
Embedding 산출
↓
pipeline_persistence
↓
embeddings
```

조회:

```text
RAG Vector Search
```

---

# 18. pgvector Retrieval

RAG Vector 검색:

```text
Question
↓
BGE-M3 Query Embedding
↓
PostgreSQL + pgvector
↓
cosine distance
```

현재 검색 범위에는 다음 조건이 포함된다.

```text
system_state.active_collection_run_id
요청 announcement_id
ProcessingRun.is_active = true
ChunkSet.is_active = true
Chunk.status = completed
Embedding.status = completed
Embedding.model_name = 현재 검색 Model
Embedding.dimension = 1024
Embedding.normalized = true
Embedding.embedding IS NOT NULL
```

Vector Search 결과는 Keyword Search 결과와 RRF로 합쳐진다.

---

# 19. KeyInformation

의미:

```text
사용자 공고 상세 화면에서 사용하는 핵심 구조화 정보
```

관계:

```text
Announcement
→ KeyInformation
```

현재 필수 데이터:

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

저장 주체:

```text
pipeline/document_processor.py
↓
extract_key_information()
↓
backend/app/services/key_information_service.py
upsert_key_information()
```

조회 주체:

```text
announcement_service
admin_service
```

`source_processing_run_id`를 통해 어느 Processing 결과에서 추출했는지 추적한다.

---

# 20. SystemState

서비스 전체에서 한 Row만 사용하는 singleton Model이다.

Constraint:

```text
id = 1
```

핵심 Column:

```text
active_collection_run_id
```

의미:

```text
현재 사용자 서비스에 노출되는 CollectionRun
```

Publish:

```text
collection_publish_service.publish_collection_run()
↓
system_state.active_collection_run_id 변경
```

사용자 Announcement 조회와 RAG는 이 값을 기준으로 서비스 데이터 범위를 제한한다.

관리자 조회는 운영 전체 데이터를 관리하기 위한 API이므로 Active Collection에만 제한되지 않는다.

---

# 21. Publish와 DB

전체 신규 수집이 성공했다고 자동으로 사용자에게 보이는 것은 아니다.

현재 Integration 흐름에서는 다음 조건을 만족할 때 Publish Service를 호출한다.

```text
CollectionRun.status = success
AND
analysis_document_ids processing failed_count = 0
```

Publish 검증에는 다음이 포함된다.

```text
Collection count 정합성
unknown Document 없음
primary Document download completed
active ProcessingRun
ProcessingRun succeeded / verification pass
active completed ChunkSet
Chunk count 정합성
모든 Chunk completed
필수 Embedding 완료
Embedding model / dimension / normalized 조건
```

검증이 성공하면:

```text
system_state.active_collection_run_id
```

를 새 Collection으로 변경한다.

---

# 22. 재처리와 Active 데이터

현재 active Collection에 속한 Document를 재처리하는 경우:

```text
새 ProcessingRun 생성
↓
새 ChunkSet / Chunk / Embedding
↓
KeyInformation
↓
activate_processing_run()
```

이 경우에는 Collection 자체를 바꾸는 작업이 아니므로 다시 Publish할 필요가 없다.

핵심은:

```text
Document별 active ProcessingRun
Document별 active ChunkSet
```

전환이다.

실패 시 기존 active 정상 데이터를 보호한다.

---

# 23. ErrorLog

공통 저장 진입점:

```text
backend/app/services/error_log_service.py
record_error()
```

지원 영역 예:

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

관계 식별자가 전달되면 다음 운영 객체와 연결될 수 있다.

```text
CollectionRun
Announcement
Document
ProcessingRun
```

RAG Hybrid Retrieval 오류와 Generation 오류도 현재 Backend 공통 ErrorLog를 사용한다.

Docker 분리 후에는 이 `Python import → DB` 구조를 어떻게 유지할지 결정해야 한다.

---

# 24. Glossary

Glossary는 Collection snapshot과 독립된 운영 테이블이다.

주요 개념:

```text
term
definition
category
is_active
created_at
updated_at
```

사용:

```text
GET /api/glossary
GET /api/admin/glossary
POST /api/admin/glossary
PUT /api/admin/glossary/{id}
PATCH /api/admin/glossary/{id}/status
DELETE /api/admin/glossary/{id}
```

저장/조회 주체:

```text
backend/app/services/glossary_service.py
```

---

# 25. Admin

관리자 인증/운영을 위한 Model이다.

현재 Admin 인증 Runtime은 환경변수 기반 인증 로직과 JWT Cookie를 사용한다.

DB Model 자체가 존재하지만 실제 로그인 계약의 최종 기준은 다음 코드다.

```text
backend/app/services/admin_auth_service.py
backend/app/api/routes/admin_auth.py
```

Admin 관련 세부 인증 구조는 `docs/API.md`를 참고한다.

---

# 26. 누가 어떤 테이블을 저장 / 조회하는가

Docker 분리 시 가장 중요한 DB Ownership 참고표다.

| 데이터 | 주요 저장 주체 | 주요 조회 주체 |
|---|---|---|
| CollectionRun | Collection Service | Admin, Publish |
| Announcement | Collection Service / Evaluation Service | User API, Admin, RAG |
| Document | Collection Service / Evaluation Service | Admin, Document Processor |
| ProcessingRun | Pipeline Persistence | Admin, Publish, RAG |
| DocumentStructure | Pipeline Persistence | Pipeline/운영 확인 |
| ChunkSet | Pipeline Persistence | Publish, RAG |
| Chunk | Pipeline Persistence | RAG |
| Embedding | Pipeline Persistence | RAG Vector Search |
| KeyInformation | KeyInformation Service | User Detail, Admin |
| SystemState | Collection Publish Service | User API, RAG |
| ErrorLog | Backend / Integration / RAG / LLM | Admin |
| Glossary | Glossary Service | User/Admin Glossary API |

중요:

현재 단일 애플리케이션 코드베이스에서는 여러 파트가 같은 DB를 직접 접근한다.

Docker를 나눈다고 자동으로 “DB write owner”가 하나로 정리되는 것은 아니다.

---

# 27. SQLAlchemy Session

파일:

```text
backend/app/db/session.py
```

Engine:

```python
create_engine(
    database_url,
    pool_pre_ping=True,
)
```

Session Factory:

```text
SessionLocal
```

FastAPI 요청용:

```text
get_db()
```

Service / Pipeline / RAG 내부에서는 `SessionLocal()` 또는 `SessionLocal.begin()`을 직접 사용하는 코드도 존재한다.

따라서 Docker 분리 시 각 Container에 DB 환경변수와 psycopg/SQLAlchemy dependency가 필요한지 확인해야 한다.

---

# 28. Alembic

Schema Migration 기준:

```text
alembic.ini
migrations/env.py
migrations/versions/
```

원칙:

```text
ORM Model 변경
↓
Alembic Migration 작성
↓
Migration 적용
↓
Runtime
```

새 DB를 만드는 경우에도 Schema는 Alembic으로 맞춰야 한다.

운영 DB에 수동 DDL을 넣고 Migration과 분리된 상태로 두면 안 된다.

---

# 29. pgvector Extension 초기화 주의

현재 Docker 초기화 파일:

```text
infra/postgres/init/01-enable-vector.sql
```

은 PostgreSQL Docker 초기 Cluster 초기화 경로에서 사용된다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

중요:

`/docker-entrypoint-initdb.d`는 기존 데이터 Volume이 이미 초기화된 상태에서는 매 Container restart마다 다시 실행되는 일반 Migration 경로가 아니다.

또한 같은 PostgreSQL Instance 안에 **새 Database를 별도로 생성할 경우**, 그 Database에도 `vector` Extension이 필요하다.

평가 DB 생성 Script는 이 때문에 `one_cycle_evaluation_tmp` 생성 후 vector를 명시적으로 활성화한다.

---

# 30. 평가 DB

운영:

```text
one_cycle
```

평가:

```text
one_cycle_evaluation_tmp
```

평가 목적:

```text
운영 DB에 없는 평가 문서를
운영 데이터와 섞지 않고
동일 Schema / Pipeline / RAG 경로로 검증
```

평가 DB 생성:

```text
backend/scripts/evaluation/create_evaluation_db.py
```

동작:

```text
Database 생성
↓
CREATE EXTENSION vector
↓
Alembic upgrade head
↓
Schema / extension 검증
```

평가 DB 삭제:

```text
backend/scripts/evaluation/drop_evaluation_db.py
```

운영 DB와 평가 DB는 서로 다른 `system_state`를 갖는다.

따라서 평가 DB에서 Publish해도 운영 DB의 `active_collection_run_id`를 변경하지 않는다.

상세:

```text
docs/BACKEND_DB_EVALUATION_WORKFLOW.md
```

---

# 31. AWS Runtime 검증 결과

> **검증 범위:** 아래 수치는 2026-08-26 AWS에서
> `develop@476575c`를 기준으로 실제 실행하여 확인한 결과다.
> 현재 문서 기준 Commit인 `develop@1c3b2e9` 전체에 대한 재검증 결과를
> 의미하지 않는다.

2026-08-26 실제 AWS 전체 수집 검증:

```text
CollectionRun ID: 2
Announcement: 50
Document: 86

primary: 48
supporting: 38
unknown: 0
```

Document Processing:

```text
requested: 48
success: 48
failed: 0
```

Active Processing:

```text
ProcessingRun: 48
ChunkSet: 48
```

저장:

```text
Chunk: 13,863
Embedding: 13,863
```

Embedding:

```text
dimension: 1024
normalized: true
```

Publish:

```text
previous active CollectionRun: 1
new active CollectionRun: 2
```

User Announcement API와 DB Announcement ID도 정확히 일치하는 것을 확인했다.

전체 기록:

```text
docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md
```

---

# 32. DB 정상 확인 방법

## 32.1 Container

```bash
docker ps
```

확인:

```text
one-cycle-postgres
healthy
```

## 32.2 Backend DB Health

```bash
curl -i http://127.0.0.1:18000/api/health/db
```

## 32.3 SQLAlchemy 직접 연결

현재 AWS 절대경로를 먼저 확인한 뒤 Repository Root에서 실행한다.

```bash
cd <PROJECT_ROOT>

PYTHONPATH=. python - <<'PY'
from sqlalchemy import text
from backend.app.db.session import engine

with engine.connect() as conn:
    print(
        "db:",
        conn.execute(
            text("SELECT current_database()")
        ).scalar_one(),
    )
    print(
        "select1:",
        conn.execute(
            text("SELECT 1")
        ).scalar_one(),
    )
PY
```

## 32.4 pgvector

```sql
SELECT extname
FROM pg_extension
WHERE extname = 'vector';
```

정상:

```text
vector
```

---

# 33. DB 데이터 보존 원칙

현재 PostgreSQL은 Named Volume을 사용한다.

```text
one-cycle-postgres-data
```

따라서:

```text
Container
≠
DB Data
```

Container를 재생성하더라도 같은 Volume을 Mount하면 데이터가 유지될 수 있다.

반대로 Volume을 삭제하면 영구 데이터가 사라질 수 있다.

다음 명령은 의미를 이해하지 않은 상태에서 사용하면 안 된다.

```text
docker compose down -v
docker volume rm ...
```

현재 AWS DB 데이터를 초기화하거나 Volume을 삭제하지 않는다.

---

# 34. Docker 운영안의 Bind Mount 제안

AWS Docker 운영안에는 향후 PostgreSQL 저장 경로를 Host Bind Mount로 명확히 하는 방안도 제시되어 있다.

예:

```text
/home/ubuntu/ddokbot/storage/postgres
→
/var/lib/postgresql/data
```

하지만 현재 실제 Compose는 Named Volume이다.

현재:

```text
one-cycle-postgres-data
```

운영안 제안:

```text
Host Bind Mount
/home/ubuntu/ddokbot/storage/postgres
```

**이 둘은 현재와 미래 계획을 구분해야 한다.**

Bind Mount로 변경할 경우 기존 Named Volume 데이터의 안전한 Migration / Backup 계획 없이 바로 경로를 바꾸면 안 된다.

---

# 35. Docker 분리 전 DB 확인 사항

## 35.1 DB 접근 주체

목표 Container:

```text
backend
rag
document-worker
postgres
```

현재 구조를 그대로 옮기면 세 Container가 DB에 직접 접근하게 된다.

```text
backend → DB
rag → DB
document-worker → DB
```

팀에서 이 구조를 유지할지, DB Write를 특정 Service로 제한할지 결정해야 한다.

현재 코드는 전자를 전제로 작성되어 있다.

## 35.2 Hostname

현재 Host 실행:

```env
POSTGRES_HOST=127.0.0.1
```

Docker 내부 목표:

```env
POSTGRES_HOST=postgres
```

`127.0.0.1`은 Container 내부 자기 자신이므로 다른 Container의 PostgreSQL을 의미하지 않는다.

## 35.3 Port 공개

현재 Compose:

```text
127.0.0.1:5432 → postgres:5432
```

모든 서비스가 Docker Network 내부로 들어간 뒤에는 PostgreSQL 외부 Host Port 공개가 필수인지 다시 검토할 수 있다.

AWS 운영안의 최종 목표는 DB를 내부 전용으로 두는 것이다.

## 35.4 Migration 실행 주체

Docker 분리 전에 결정:

```text
backend startup이 migration 실행?
별도 one-shot migration service?
운영자가 수동 실행?
```

여러 Container가 동시에 `alembic upgrade`를 실행하게 만들면 안 된다.

## 35.5 File / DB 경로

`documents.storage_path`에는 원본 파일 위치가 들어 있다.

Document Worker Container가 이 경로를 실제로 열 수 있어야 한다.

Host 절대경로가 DB에 저장되어 있으면 Container에서 동일 문자열이 존재하지 않을 수 있다.

결정 필요:

```text
Host Path
Container Path
공통 Storage Root
DB에 저장할 Canonical Path
```

## 35.6 Persistent Storage

결정:

```text
Named Volume 유지
또는
Bind Mount 전환
```

현재 데이터 보존이 최우선이다.

## 35.7 Backup

Container 분리/Volume 이전 전에 최소한 다음을 준비해야 한다.

```text
DB dump
Volume 경로 확인
복구 방법
Migration version 확인
```

---

# 36. Docker 목표 DB 연결도

```text
              ┌──────────────┐
              │   Backend    │
              └──────┬───────┘
                     │ SQLAlchemy
                     │
┌──────────────┐     │
│     RAG      ├─────┼──────────┐
└──────────────┘     │          │
      SQLAlchemy     │          │
                     ▼          │
              ┌──────────────┐  │
              │  PostgreSQL  │◀─┘
              │  + pgvector  │
              └──────▲───────┘
                     │
               SQLAlchemy /
               Persistence
                     │
          ┌──────────┴──────────┐
          │   Document Worker   │
          └─────────────────────┘
```

이 구조에서는 PostgreSQL Container의 Network / Credential / Migration / Volume 정책이 세 서비스 모두에 영향을 준다.

---

# 37. 현재 한계 / 주의

- PostgreSQL은 이미 Docker지만 나머지 주요 서비스는 아직 Host Process다.
- Backend / RAG / Pipeline이 같은 DB를 직접 사용한다.
- `storage_path`는 File System 구조와 DB를 결합한다.
- RAG는 pgvector뿐 아니라 Keyword Search와 RRF도 사용한다.
- Active Collection은 `SystemState`로 결정된다.
- Document 재처리는 ProcessingRun / ChunkSet 버전 구조를 사용한다.
- supporting Document는 현재 RAG index 대상이 아니다.
- 새 Database에는 vector Extension을 별도로 확인해야 한다.
- 사용자 원본 파일 URL은 현재 Announcement Detail DB/API 계약에 포함되어 있지 않다.
- Docker Bind Mount 전환은 현재 Named Volume 데이터 Migration과 별도 문제다.

---

# 38. Source of Truth

| 영역 | 기준 |
|---|---|
| DB Session | `backend/app/db/session.py` |
| ORM | `backend/app/models/` |
| Migration | `migrations/versions/` |
| Alembic Runtime | `migrations/env.py` |
| Collection Persistence | `backend/app/services/collection_service.py` |
| Pipeline Persistence | `backend/app/services/pipeline_persistence.py` |
| KeyInformation | `backend/app/services/key_information_service.py` |
| Publish | `backend/app/services/collection_publish_service.py` |
| User DB Query | `backend/app/services/announcement_service.py` |
| Admin DB Query | `backend/app/services/admin_service.py` |
| ErrorLog | `backend/app/services/error_log_service.py` |
| Glossary | `backend/app/services/glossary_service.py` |
| RAG Vector SQL | `rag/db_pipeline.py` |
| RAG Keyword SQL | `rag/retrieval/keyword_search.py` |
| PostgreSQL Compose | `infra/docker-compose.yml` |
| pgvector Init | `infra/postgres/init/01-enable-vector.sql` |
| Evaluation DB | `backend/scripts/evaluation/`, `backend/app/services/evaluation_*` |

---

# 39. 관련 문서

```text
docs/BACKEND.md
→ Backend / DB 전체 흐름

docs/API.md
→ Endpoint / Schema / Frontend 계약

docs/ENVIRONMENT.md
→ AWS / Port / 환경변수

docs/BACKEND_INTEGRATION.md
→ Pipeline / RAG 통합

docs/BACKEND_DB_EVALUATION_WORKFLOW.md
→ 평가 DB

docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md
→ 실제 AWS 데이터 검증
```

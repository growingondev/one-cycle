# DDOKBOT Database Architecture

> 이 문서는 DDOKBOT의 PostgreSQL + pgvector 데이터 구조와  
> Pipeline Persistence, Active Dataset, Runtime RAG 사이의 연결을 설명합니다.
>
> 새로운 개발자 또는 AI가 다음 내용을 이해할 수 있도록 작성되었습니다.
>
> - 어떤 ORM Model이 존재하는지
> - Pipeline 결과가 어떤 순서로 DB에 저장되는지
> - ProcessingRun과 ChunkSet이 왜 존재하는지
> - Active 상태가 Runtime RAG 검색에 어떻게 영향을 주는지
> - pgvector Embedding이 어디에 저장되는지
> - Alembic Migration을 어디에서 관리하는지
> - DB 관련 문제가 발생하면 어느 파일을 확인해야 하는지

---

# 1. Database Stack

현재 DDOKBOT의 Database Stack:

```text
PostgreSQL
+
pgvector
+
SQLAlchemy
+
Alembic
```

역할:

```text
PostgreSQL
→ Application 데이터 저장

pgvector
→ Embedding Vector 저장 및 Similarity Search

SQLAlchemy
→ Python ORM / DB Session

Alembic
→ DB Schema Migration 관리
```

---

# 2. 관련 디렉터리

```text
backend/app/db/
backend/app/models/
backend/app/services/pipeline_persistence.py

migrations/
alembic.ini

infra/docker-compose.yml
infra/postgres/init/01-enable-vector.sql
```

---

# 3. Database Connection

DB Session 관련 코드:

```text
backend/app/db/session.py
```

SQLAlchemy Base:

```text
backend/app/db/base.py
```

Application과 RAG 모두 동일한 Backend DB Session 구성을 사용합니다.

개념:

```text
Backend Service
      │
      ├────────────┐
      ▼            ▼
SQLAlchemy      RAG Pipeline
      │            │
      └─────┬──────┘
            ▼
       PostgreSQL
```

RAG 내부에서 별도의 독립적인 DB 연결 설정을 새로 만들지 않고,
공통 `SessionLocal`을 사용하는 구조입니다.

---

# 4. Database Models

현재 ORM Model 위치:

```text
backend/app/models/
```

현재 확인된 주요 Model:

```text
admin.py
announcement.py
chunk.py
chunk_set.py
collection_run.py
document.py
document_structure.py
embedding.py
error_log.py
key_information.py
processing_artifact.py
processing_run.py
system_state.py
```

실제 Column과 Foreign Key의 최종 기준은 각 Model 파일입니다.

---

# 5. 전체 데이터 관계 개념

현재 시스템을 이해할 때 핵심 관계는 다음과 같습니다.

```text
CollectionRun
     │
     ▼
Announcement
     │
     ▼
Document
     │
     ├────────────────────┐
     │                    │
     ▼                    ▼
ProcessingRun       DocumentStructure
     │
     ▼
ChunkSet
     │
     ▼
Chunk
     │
     ▼
Embedding
```

추가 Application 데이터:

```text
KeyInformation
Admin
ErrorLog
SystemState
ProcessingArtifact
```

정확한 Foreign Key 방향은 ORM Model을 Source of Truth로 확인합니다.

---

# 6. CollectionRun

파일:

```text
backend/app/models/collection_run.py
```

역할:

공고 데이터가 어느 수집/등록 실행 단위에 속하는지를 표현하기 위한 Model입니다.

개념:

```text
Collection Run
      ↓
Announcements
```

Runtime RAG에서는 `system_state`의 Active Collection과 연결하여
현재 서비스 대상 공고를 제한할 수 있습니다.

---

# 7. Announcement

파일:

```text
backend/app/models/announcement.py
```

서비스에서 사용자에게 노출되는 공고 단위입니다.

예:

```text
공고 ID = 1
```

Frontend가 Chat 요청을 보낼 때:

```json
{
  "announcementId": 1
}
```

처럼 이 공고 ID를 전달합니다.

Runtime RAG는 이 ID를 검색 범위 조건으로 사용합니다.

---

# 8. Document

파일:

```text
backend/app/models/document.py
```

Announcement와 연결된 실제 문서 단위입니다.

개념:

```text
Announcement
    ↓
Document
```

하나의 공고에 실제 HWP/HWPX 문서가 연결될 수 있으며,
Pipeline Processing은 Document를 중심으로 실행됩니다.

---

# 9. ProcessingRun

파일:

```text
backend/app/models/processing_run.py
```

특정 Document에 대해 Pipeline을 실행한 한 번의 처리 결과를 나타냅니다.

예:

```text
Document 1
 ├── ProcessingRun 1
 ├── ProcessingRun 2
 ├── ProcessingRun 3
 ├── ProcessingRun 4
 └── ProcessingRun 5
```

현재 실제 검증에서 다음 상태가 확인되었습니다.

```text
id=1 active=False
id=2 active=False
id=3 active=False
id=4 active=False
id=5 active=True
```

즉 동일 문서를 여러 번 재처리하더라도 과거 결과를 즉시 삭제하는 대신
별도의 ProcessingRun으로 보관할 수 있습니다.

---

# 10. ProcessingRun이 필요한 이유

문서를 다시 Pipeline 처리하면 기존 데이터를 바로 덮어쓰는 방식보다
새 ProcessingRun을 생성하는 방식이 안전합니다.

개념:

```text
Old ProcessingRun
      │
      │ 아직 서비스 중
      ▼
Active = TRUE

새 Pipeline 실행
      ↓
New ProcessingRun
      ↓
Validation
      ↓
DB Write
      ↓
Activation
      ↓
Old Run Active = FALSE
New Run Active = TRUE
```

이 구조를 사용하면 새 데이터가 완전히 준비되기 전에
기존 서비스 데이터를 잃지 않을 수 있습니다.

---

# 11. ProcessingArtifact

파일:

```text
backend/app/models/processing_artifact.py
```

Pipeline 실행 과정에서 생성되는 처리 Artifact와 관련된 정보를 관리하는 Model입니다.

정확한 Artifact 종류와 Column 정의는 해당 Model 및 Persistence 코드를 확인합니다.

---

# 12. DocumentStructure

파일:

```text
backend/app/models/document_structure.py
```

Structure Pipeline 결과와 관련된 데이터를 DB에 보관하기 위한 영역입니다.

Pipeline 흐름:

```text
Normalized Document
      ↓
Structure Pipeline
      ↓
Structured Result
      ↓
Persistence
      ↓
DocumentStructure
```

---

# 13. ChunkSet

파일:

```text
backend/app/models/chunk_set.py
```

특정 ProcessingRun에서 생성된 Chunk들의 집합입니다.

개념:

```text
ProcessingRun
      ↓
ChunkSet
      ↓
Chunks
```

ChunkSet에도 Active 상태가 존재합니다.

Runtime RAG에서는:

```text
ProcessingRun.is_active = TRUE
AND
ChunkSet.is_active = TRUE
```

인 데이터를 대상으로 검색합니다.

---

# 14. Chunk

파일:

```text
backend/app/models/chunk.py
```

RAG Retrieval의 실제 검색 단위입니다.

Pipeline:

```text
Structured Document
      ↓
Chunking
      ↓
Chunk
```

DB에는 Chunk의 의미를 유지할 수 있도록 다음 성격의 정보가 저장됩니다.

```text
Chunk ID
Announcement relation
Document relation
ChunkSet relation
Document Format
Content Type
Section Path
Title
Content
Search Text
Source Reference
Status
```

정확한 Column 이름과 타입은 `chunk.py`를 최종 기준으로 확인합니다.

---

# 15. External Chunk Key

Pipeline에서 생성한 Chunk ID와 DB의 내부 Primary Key는 서로 다른 개념입니다.

예:

```text
DB 내부 ID
5

외부 Chunk Key
계약금1_000_청주지북_..._sec_0019_tbl_0020
```

Runtime API의 Evidence에서는 사람이 추적 가능한 외부 Chunk Key가 반환될 수 있습니다.

개념:

```text
chunks.id
→ DB 내부 관계용

chunks.external_chunk_key
→ Pipeline/RAG 추적용
```

---

# 16. Embedding

파일:

```text
backend/app/models/embedding.py
```

각 Chunk에 대응하는 Vector를 저장합니다.

개념:

```text
Chunk
  ↓
Embedding
```

현재 확인된 Embedding:

```text
Model
BAAI/bge-m3

Dimension
1024

Normalized
TRUE
```

---

# 17. pgvector

PostgreSQL에 Vector 검색 기능을 제공하기 위해 pgvector를 사용합니다.

초기화 SQL:

```text
infra/postgres/init/01-enable-vector.sql
```

Runtime RAG에서는 pgvector cosine distance 연산을 사용합니다.

개념:

```sql
embedding <=> query_vector
```

Similarity는 현재 DB RAG Pipeline에서 개념적으로:

```text
1 - cosine distance
```

형태로 계산합니다.

---

# 18. Document Embedding → DB

Offline Pipeline:

```text
Chunk
  ↓
BAAI/bge-m3
  ↓
1024-d Vector
  ↓
Pipeline Output
  ↓
pipeline_persistence.py
  ↓
embeddings table
```

---

# 19. Query Embedding → DB Search

Runtime:

```text
Question
  ↓
BAAI/bge-m3
  ↓
1024-d Query Vector
  ↓
pgvector
  ↓
Stored Chunk Embeddings
  ↓
Top-K Similarity
```

따라서:

```text
Document Embedding Model
Query Embedding Model
Vector Dimension
Normalization 방식
```

이 서로 호환되어야 합니다.

---

# 20. KeyInformation

파일:

```text
backend/app/models/key_information.py
```

공고문에서 추출한 주요 구조화 정보를 저장하기 위한 영역입니다.

이 Model이 존재한다고 해서 현재 모든 Key Information Composer 기능이 완성되어 있다는 의미는 아닙니다.

현재 프로젝트에서는 Key Information 관련 기능이 추가 검증/보완 대상입니다.

정확한 현재 사용 여부는:

```text
backend/app/services/
pipeline/structure/
```

참조 관계를 확인합니다.

---

# 21. SystemState

파일:

```text
backend/app/models/system_state.py
```

현재 서비스가 어떤 Collection/DataSet을 Active로 사용해야 하는지 나타내는 상태 Model입니다.

Runtime Retrieval에서 확인된 구조:

```text
system_state
      ↓
active_collection_run_id
      ↓
collection_run
      ↓
announcement
```

즉 DB에 Announcement가 존재한다고 해서
모든 Announcement가 현재 Runtime 서비스 대상이 되는 것은 아닐 수 있습니다.

---

# 22. Runtime Retrieval의 DB Join 개념

현재 `rag/db_pipeline.py`에서 사용하는 검색 구조를 개념적으로 표현하면:

```text
SystemState
    │
    ▼
Active CollectionRun
    │
    ▼
Announcement
    │
    ▼
Chunk
    │
    ▼
ChunkSet
    │
    ▼
ProcessingRun
    │
    ▼
Embedding
```

검색 필터:

```text
선택 announcement_id

ChunkSet.is_active = TRUE

ProcessingRun.is_active = TRUE

Chunk.status = completed

Embedding.status = completed

Embedding.model_name = 현재 Query Embedding Model

Embedding.dimension = 1024

Embedding.normalized = TRUE

Embedding Vector IS NOT NULL
```

실제 SQL의 최종 기준:

```text
rag/db_pipeline.py
```

---

# 23. Active ProcessingRun과 Active ChunkSet

Runtime 검색에서 가장 중요한 조건 중 하나입니다.

정상적인 서비스 데이터:

```text
ProcessingRun.is_active = TRUE
ChunkSet.is_active = TRUE
```

예:

```text
processing_run_id = 5
processing_run_active = True

chunk_set_id = 5
chunk_set_active = True

chunk_count = 291
```

이 상태라면 해당 Processing 결과가 Runtime RAG 검색 대상입니다.

---

# 24. Persistence 과정

관련 코드:

```text
backend/app/services/pipeline_persistence.py
```

전체 흐름:

```text
Pipeline Outputs
      ↓
Validation
      ↓
Registered Document 확인
      ↓
ProcessingRun 생성
      ↓
DocumentStructure 저장
      ↓
ChunkSet 생성
      ↓
Chunk 저장
      ↓
Embedding 저장
      ↓
Commit
```

---

# 25. Persistence Dry Run

실제 DB에 쓰기 전에 검증합니다.

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m backend.app.services.pipeline_persistence \
--announcement-key announcement_001
```

정상 확인 예:

```text
DRY RUN: PASS
DB WRITE: NO
```

Dry Run에서 확인되는 주요 항목:

```text
announcement_key
document format
filename
schema version
verification
chunk count
embedding model
dimension
embedding count
announcement DB ID
document DB ID
```

---

# 26. Persistence Write

실제 DB 저장:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m backend.app.services.pipeline_persistence \
--announcement-key announcement_001 \
--write
```

현재 확인된 정상 예:

```text
processing_run_id: 5
document_structure_id: 5
chunk_set_id: 5

written_chunks: 291
written_embeddings: 291

DB WRITE: PASS
ACTIVE SWITCH: NO
```

중요:

DB Write 성공과 Active 전환은 별개입니다.

---

# 27. Activation

새 ProcessingRun을 실제 서비스 대상으로 전환할 때:

```text
activate_processing_run()
```

을 사용합니다.

예:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from backend.app.services.pipeline_persistence import (
    activate_processing_run,
)

result = activate_processing_run(5)

for key, value in result.items():
    print(f"{key}: {value}")
PY
```

정상 예:

```text
processing_run_id: 5
document_id: 1
chunk_set_id: 5
chunks: 291
embeddings: 291
deactivated_runs: [4]
```

---

# 28. Activation의 의미

Activation은 개념적으로:

```text
OLD
ProcessingRun 4
Active = TRUE

NEW
ProcessingRun 5
Active = FALSE
```

를:

```text
OLD
ProcessingRun 4
Active = FALSE

NEW
ProcessingRun 5
Active = TRUE
```

로 전환합니다.

관련 ChunkSet도 새 ProcessingRun과 일치하는 Active 상태가 되어야 합니다.

---

# 29. 왜 Write와 Activation을 분리하는가

DB Write 직후 자동으로 서비스 데이터를 교체하면
잘못된 Pipeline 결과가 즉시 사용자에게 노출될 수 있습니다.

따라서:

```text
Write
 ↓
검증
 ↓
Activation
```

을 분리합니다.

이 방식은 운영 안정성을 높입니다.

---

# 30. DB Connection Test

가장 간단한 연결 확인:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from sqlalchemy import text
from backend.app.db.session import engine

with engine.connect() as conn:
    value = conn.execute(
        text("SELECT 1")
    ).scalar_one()

print("[OK] DB CONNECTION:", value)
PY
```

정상:

```text
[OK] DB CONNECTION: 1
```

---

# 31. DB 연결 실패 시 확인 순서

```text
1. PostgreSQL Process/Container 실행 여부
2. .env Database 설정
3. backend/app/core/config.py
4. backend/app/db/session.py
5. DB User
6. DB Password
7. Host
8. Port
9. Database Name
```

예전에 실제로 확인된 오류:

```text
password authentication failed
```

이 경우 Pipeline/RAG 코드를 수정하는 것이 아니라
DB 인증 설정을 확인합니다.

---

# 32. Alembic

DB Schema Version 관리:

```text
alembic.ini
migrations/
```

구조:

```text
migrations/
├── env.py
├── script.py.mako
└── versions/
```

---

# 33. 현재 Migration 영역

현재 Migration 파일 이름 기준으로 다음 구조가 순차적으로 추가되었습니다.

```text
Announcements

Collection Runs
Documents

Processing Runs
Processing Artifacts

Chunk / Embedding Schema

Document Structures
Key Information

Active Dataset State

Admin
Error Log
```

정확한 Revision 순서와 Schema 내용은:

```text
migrations/versions/
```

의 실제 Alembic Revision을 확인합니다.

---

# 34. Model 변경 시 Migration

ORM Model만 수정하고 끝내면 안 됩니다.

기본 원칙:

```text
Model 변경
    ↓
Alembic Migration 작성
    ↓
Migration Review
    ↓
alembic upgrade head
    ↓
DB Schema 적용
```

---

# 35. alembic.ini 위치

현재:

```text
/home/ubuntu/ddokbot/one-cycle/alembic.ini
```

이 위치가 정상입니다.

`alembic.ini`는:

```text
DB 데이터 파일 X
Backend Model 파일 X
```

입니다.

역할:

```text
Alembic CLI Configuration
```

따라서 Project Root에 두는 것이 일반적인 구조입니다.

---

# 36. pgvector 초기화

파일:

```text
infra/postgres/init/01-enable-vector.sql
```

PostgreSQL Container 초기화 시 pgvector Extension을 사용할 수 있도록 설정합니다.

DB를 새로 만드는 경우 pgvector Extension이 존재하는지 반드시 확인합니다.

---

# 37. Runtime RAG와 DB 관계

Runtime RAG는:

```text
outputs/
```

를 직접 검색하지 않습니다.

현재 서비스 구조:

```text
outputs/
   ↓
Persistence
   ↓
PostgreSQL
   ↓
Runtime RAG
```

즉 Pipeline 산출물은 Persistence 이후 DB 검색 데이터로 전환됩니다.

---

# 38. DB에 데이터는 있는데 RAG 검색이 안 되는 경우

다음 순서로 확인합니다.

```text
1. Announcement ID가 맞는가?
2. Announcement가 Active Collection에 속하는가?
3. Document가 연결되어 있는가?
4. Active ProcessingRun이 존재하는가?
5. Active ChunkSet이 존재하는가?
6. Chunk Status가 completed인가?
7. Embedding Status가 completed인가?
8. Embedding Model이 일치하는가?
9. Dimension이 1024인가?
10. normalized가 TRUE인가?
11. Embedding Vector가 NULL이 아닌가?
```

---

# 39. Active Run 확인 예

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from sqlalchemy import select
from backend.app.db.session import SessionLocal
from backend.app.models import ProcessingRun

with SessionLocal() as db:
    rows = db.scalars(
        select(ProcessingRun)
        .where(
            ProcessingRun.document_id == 1
        )
        .order_by(
            ProcessingRun.id
        )
    ).all()

for row in rows:
    print(
        "id=", row.id,
        "active=", row.is_active,
    )
PY
```

정상적으로는 동일 Document에 대해
최종 서비스 대상 Run 하나만 Active가 되어야 합니다.

---

# 40. Active ChunkSet 확인

개념 SQL:

```sql
SELECT
    pr.id,
    pr.is_active,
    cs.id,
    cs.is_active,
    COUNT(c.id)
FROM processing_runs pr
JOIN chunk_sets cs
  ON cs.processing_run_id = pr.id
JOIN chunks c
  ON c.chunk_set_id = cs.id
WHERE pr.document_id = :document_id
  AND pr.is_active = TRUE
  AND cs.is_active = TRUE
GROUP BY
    pr.id,
    pr.is_active,
    cs.id,
    cs.is_active;
```

목적:

```text
현재 Runtime 서비스 대상 Chunk 수 확인
```

---

# 41. Chunk와 Embedding Count

Persistence 검증에서 중요한 조건:

```text
Chunk Count
=
Embedding Count
```

예:

```text
chunks: 291
embeddings: 291
```

Chunk 291개인데 Embedding이 290개라면
Runtime 검색 전에 Persistence/Embedding Pipeline을 확인해야 합니다.

---

# 42. Embedding Integrity

현재 정상 검증 예:

```text
model: BAAI/bge-m3
dimension: 1024

embedding_count: 291

norm_min ≈ 1.0
norm_max ≈ 1.0
```

L2 Normalized Vector이므로 norm이 약 1.0이어야 합니다.

---

# 43. DB Schema를 변경할 때 영향 범위

## Chunk Column 변경

확인:

```text
backend/app/models/chunk.py
backend/app/services/pipeline_persistence.py
rag/db_pipeline.py
backend/app/schemas/
migrations/
```

---

## Embedding Column 변경

확인:

```text
backend/app/models/embedding.py
pipeline/embedding/
pipeline_persistence.py
rag/retrieval/query_embedding.py
rag/db_pipeline.py
migrations/
```

---

## ProcessingRun 구조 변경

확인:

```text
processing_run.py
chunk_set.py
pipeline_persistence.py
rag/db_pipeline.py
admin_service.py
migrations/
```

---

## Announcement 구조 변경

확인:

```text
announcement.py
announcement_service.py
schemas/announcement.py
routes/announcements.py
rag/db_pipeline.py
frontend/user/
migrations/
```

---

# 44. Database와 Frontend의 관계

Frontend는 Database에 직접 연결하지 않습니다.

항상:

```text
Frontend
   ↓
FastAPI
   ↓
Service
   ↓
Database
```

구조입니다.

예:

```text
ListScreen
  ↓
GET /api/announcements
  ↓
Announcement Service
  ↓
Database
```

---

# 45. Database와 Pipeline의 관계

Pipeline 역시 가능하면 ORM/DB 세부 구현에 직접 섞이지 않습니다.

구조:

```text
pipeline/
   ↓
Pipeline Output
   ↓
pipeline_persistence.py
   ↓
Database
```

이 경계를 유지하면 Pipeline 알고리즘과 DB 저장 정책을 독립적으로 수정하기 쉬워집니다.

---

# 46. Database와 RAG의 관계

RAG는 현재 DB에 저장된 Chunk와 Embedding을 Runtime Retrieval 대상으로 사용합니다.

```text
PostgreSQL
   ↓
rag/db_pipeline.py
   ↓
Retrieved Chunks
   ↓
Generation
```

따라서:

```text
Pipeline Output만 존재
DB Persistence 안 함
```

상태에서는 Runtime RAG 검색 대상이 아닐 수 있습니다.

---

# 47. DB 문제 진단 Matrix

| 증상 | 우선 확인 |
|---|---|
| DB 연결 자체 실패 | `.env`, `session.py`, PostgreSQL |
| Announcement 목록 없음 | `announcements`, Collection 상태 |
| Chunk 없음 | Persistence, ChunkSet |
| Embedding 없음 | Embedding Pipeline, Persistence |
| Vector 검색 결과 없음 | Active 상태, Model, Dimension |
| 이전 데이터가 검색됨 | ProcessingRun/ChunkSet Active |
| 새 Pipeline 결과가 검색 안 됨 | Activation |
| Vector Dimension 오류 | Embedding Model/DB Schema |
| Migration 오류 | `alembic.ini`, `migrations/` |

---

# 48. AI에게 DB 문제를 맡길 때 제공할 파일

최소:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/PIPELINE.md
docs/RAG.md
docs/DATABASE.md

backend/app/db/
backend/app/models/
backend/app/services/pipeline_persistence.py

migrations/
alembic.ini

rag/db_pipeline.py
```

Infrastructure 문제라면 추가:

```text
infra/
.env.example
```

실제 `.env`에는 Secret이 포함될 수 있으므로
AI나 외부 사람에게 그대로 공유하기 전에 값을 반드시 확인합니다.

---

# 49. Database Source of Truth

| 영역 | Source of Truth |
|---|---|
| DB Connection | `backend/app/db/session.py` |
| SQLAlchemy Base | `backend/app/db/base.py` |
| ORM Models | `backend/app/models/` |
| Pipeline Persistence | `backend/app/services/pipeline_persistence.py` |
| Runtime Retrieval SQL | `rag/db_pipeline.py` |
| Migration Config | `alembic.ini` |
| Migration Environment | `migrations/env.py` |
| Schema History | `migrations/versions/` |
| PostgreSQL Infra | `infra/docker-compose.yml` |
| pgvector Init | `infra/postgres/init/01-enable-vector.sql` |

---

# 50. 핵심 요약

현재 DDOKBOT의 DB 흐름은 다음과 같습니다.

```text
HWP/HWPX
   ↓
Pipeline
   ↓
Chunks + Embeddings
   ↓
Persistence
   ↓
ProcessingRun
   ↓
ChunkSet
   ↓
Chunks
   ↓
Embeddings
   ↓
Activation
   ↓
PostgreSQL + pgvector
   ↓
Runtime RAG
```

가장 중요한 개념은 다음 세 가지입니다.

```text
1. DB Write와 Activation은 별개다.

2. Runtime RAG는 Active ProcessingRun과
   Active ChunkSet을 검색 대상으로 사용한다.

3. Pipeline Output이 존재한다고 해서
   Runtime RAG에서 자동으로 검색 가능한 것은 아니다.
   Persistence와 Activation까지 완료되어야 한다.
```

DB 관련 문제를 수정할 때는 Pipeline, Backend, RAG 전체를 한꺼번에 변경하지 말고
먼저 문제가 다음 중 어디인지 구분합니다.

```text
Connection
Schema
Persistence
Activation
Retrieval
```

그 다음 해당 계층만 수정합니다.
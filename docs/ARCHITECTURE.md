# DDOKBOT Architecture

> 이 문서는 DDOKBOT의 전체 시스템 연결 구조와 각 모듈 사이의 책임 경계를 설명합니다.  
> 새로운 개발자나 AI가 프로젝트를 처음 인수받았을 때, 어떤 코드가 어떤 코드를 호출하고 어떤 데이터가 어디로 이동하는지 이해하기 위한 문서입니다.

---

## 1. 전체 Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                         FRONTEND                            │
│                                                             │
│   User Frontend                         Admin Frontend       │
│   React + TypeScript + Vite             HTML + JS           │
│   frontend/user/                        frontend/admin/      │
└───────────────────┬──────────────────────────┬───────────────┘
                    │                          │
                    └────────── /api ──────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                          BACKEND                            │
│                                                             │
│                          FastAPI                            │
│                  backend/app/main.py                        │
│                                                             │
│   Routes → Schemas → Services → DB / Pipeline / RAG        │
└───────────────────────┬──────────────────────┬──────────────┘
                        │                      │
                        │                      │
                        ▼                      ▼
              ┌──────────────────┐    ┌────────────────────┐
              │   PostgreSQL     │    │        RAG         │
              │   + pgvector     │◀───│  rag/db_pipeline.py│
              └────────▲─────────┘    └─────────┬──────────┘
                       │                        │
                       │                        ▼
                       │              ┌────────────────────┐
                       │              │     Generation     │
                       │              │ rag/generation/    │
                       │              └────────────────────┘
                       │
                       │ Persistence
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                    DOCUMENT PIPELINE                        │
│                                                             │
│ Parser → Normalizer → Structure → Chunking → Embedding     │
│                                                             │
│                         pipeline/                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 시스템을 두 흐름으로 구분해서 이해하기

DDOKBOT은 크게 **문서 등록/처리 흐름**과 **사용자 질의응답 흐름**으로 나뉩니다.

### 문서 등록/처리 흐름

```text
HWP / HWPX
    ↓
Parser
    ↓
Normalizer
    ↓
Structure
    ↓
Chunking
    ↓
Embedding
    ↓
Persistence
    ↓
PostgreSQL + pgvector
```

이 흐름은 원본 문서를 RAG가 검색할 수 있는 형태로 만드는 과정입니다.

### 사용자 질의응답 흐름

```text
사용자 질문
    ↓
FastAPI /api/chat
    ↓
RAG Service
    ↓
Query Embedding
    ↓
PostgreSQL + pgvector Retrieval
    ↓
관련 Chunk 검색
    ↓
Generation
    ↓
Answer + Evidence
```

즉 사용자가 질문할 때마다 HWP/HWPX Parser부터 다시 실행하는 구조가 아닙니다.

---

## 3. Document Pipeline Architecture

전체 Pipeline의 상위 진입점:

```text
run_pipeline.py
```

현재 연결 구조:

```text
run_pipeline.py
    │
    ├── pipeline/parser/hwp_parser.py
    │
    ├── pipeline/parser/hwpx_parser.py
    │
    ├── pipeline/normalizer/document_normalizer.py
    │
    ├── pipeline/structure/run_structure.py
    │
    ├── pipeline/chunking/run_chunking.py
    │
    ├── pipeline/embedding/run_embeddings.py
    │
    └── backend/app/services/pipeline_persistence.py
```

---

## 4. Pipeline 단계별 호출 구조

### 4.1 Parser

```text
run_pipeline.py
    ↓
parse_hwp_file()
또는
parse_hwpx_file()
    ↓
pipeline/parser/hwp_parser.py
pipeline/parser/hwpx_parser.py
```

입력:

```text
.hwp
.hwpx
```

출력:

```text
Parsed JSON
```

---

### 4.2 Normalizer

```text
run_pipeline.py
    ↓
normalize_file()
    ↓
pipeline/normalizer/document_normalizer.py
```

입력:

```text
Parsed JSON
```

출력:

```text
Normalized JSON
```

---

### 4.3 Structure

```text
run_pipeline.py
    ↓
structure_file()
    ↓
pipeline/structure/run_structure.py
```

내부:

```text
build_document_step1.py
    ↓
build_domain_step2.py
    ↓
build_table_step3.py
    ↓
finalize_structure.py
```

출력:

```text
Structured Document
```

---

### 4.4 Chunking

```text
run_pipeline.py
    ↓
chunk_file()
    ↓
pipeline/chunking/run_chunking.py
```

내부:

```text
section_walker.py
paragraph_chunker.py
table_chunker.py
text_builder.py
tokenizer.py
validator.py
```

출력:

```text
chunks.json
```

---

### 4.5 Embedding

```text
run_pipeline.py
    ↓
embed_all()
    ↓
pipeline/embedding/run_embeddings.py
```

내부:

```text
input_loader.py
    ↓
model_loader.py
    ↓
embedding_generator.py
    ↓
validator.py
    ↓
output_writer.py
```

Embedding model:

```text
BAAI/bge-m3
```

---

### 4.6 Persistence

```text
run_pipeline.py
    ↓
persist_pipeline_outputs()
    ↓
backend/app/services/pipeline_persistence.py
    ↓
SQLAlchemy
    ↓
PostgreSQL
```

Persistence는 Pipeline 산출물을 DB Runtime 데이터로 연결하는 경계입니다.

---

## 5. Output Architecture

Pipeline 산출물의 기본 Root:

```text
outputs/
```

문서별 경로 생성:

```text
config/paths.py
```

개념적으로 다음과 같은 Stage 구조를 사용합니다.

```text
outputs/
└── <announcement_id>/
    ├── 01_parsed/
    ├── 02_normalized/
    ├── 03_structured/
    ├── 04_chunks/
    └── 05_embeddings/
```

실제 경로 정의의 최종 기준은:

```text
config/paths.py
run_pipeline.py
```

입니다.

---

## 6. Backend Architecture

FastAPI Application Entry:

```text
backend/app/main.py
```

전체 Backend 구조:

```text
backend/app/
├── api/
├── core/
├── db/
├── models/
├── schemas/
├── services/
└── main.py
```

계층 흐름:

```text
HTTP Request
    ↓
API Route
    ↓
Pydantic Schema
    ↓
Application Service
    ↓
DB / RAG / Pipeline
    ↓
Response
```

---

## 7. API Router Architecture

Main Application:

```text
backend/app/main.py
```

API Router:

```text
backend/app/api/router.py
```

연결되는 주요 Router:

```text
health
announcements
chat
admin_auth
admin
```

전체 API prefix:

```text
/api
```

---

## 8. Announcement 조회 흐름

```text
User Frontend
    ↓
GET /api/announcements
    ↓
backend/app/api/routes/announcements.py
    ↓
backend/app/services/announcement_service.py
    ↓
SQLAlchemy
    ↓
PostgreSQL
```

상세 조회:

```text
GET /api/announcements/{id}
```

---

## 9. Chat 전체 호출 구조

현재 Chat은 다음 순서로 연결됩니다.

```text
frontend/user/src/components/screens/DetailScreen.tsx
    │
    │ POST /api/chat
    ▼
backend/app/api/routes/chat.py
    │
    ▼
backend/app/services/chat_service.py
    │
    │ dynamic function load
    │ RAG_ANSWER_FUNCTION
    ▼
rag.service:answer_question
    │
    ▼
rag/service.py
    │
    ▼
rag/db_pipeline.py
    │
    ├── rag/retrieval/query_embedding.py
    │
    ├── PostgreSQL + pgvector
    │
    └── rag/generation/generator.py
    │
    ▼
answer + evidence
    │
    ▼
ChatResponse
    │
    ▼
DetailScreen.tsx
```

---

## 10. Backend ↔ RAG Boundary

Backend는 RAG 내부 구현을 직접 수행하지 않습니다.

경계:

```text
backend/app/services/chat_service.py
```

환경변수:

```text
RAG_ANSWER_FUNCTION
```

현재 대상:

```text
rag.service:answer_question
```

개념적 함수 계약:

```python
answer_question(
    announcement_id,
    question,
)
```

즉 RAG 내부를 새로 구현하더라도 이 진입 계약을 유지하면 Backend 변경 범위를 최소화할 수 있습니다.

---

## 11. RAG Architecture

현재 RAG 구조:

```text
rag/
├── db_pipeline.py
├── models.py
├── service.py
├── retrieval/
│   ├── config.py
│   ├── models.py
│   └── query_embedding.py
└── generation/
    ├── config.py
    ├── context_builder.py
    ├── generator.py
    ├── llm_client.py
    ├── models.py
    └── prompt_builder.py
```

---

## 12. Runtime RAG Flow

```text
Question
    ↓
rag/service.py
    ↓
DBRAGPipeline
    ↓
Query Embedding
    ↓
BGE-M3
    ↓
1024-dimensional Vector
    ↓
PostgreSQL + pgvector
    ↓
Announcement-scoped Retrieval
    ↓
Top-K Chunks
    ↓
Generation Context
    ↓
Prompt
    ↓
LLM
    ↓
Answer
```

---

## 13. Query Embedding Architecture

관련 파일:

```text
rag/retrieval/query_embedding.py
```

모델 로딩:

```text
pipeline/embedding/model_loader.py
```

현재 문서와 질문 모두 BGE-M3 계열 Embedding을 사용합니다.

따라서 다음 두 영역은 서로 호환되어야 합니다.

```text
Document Embedding
pipeline/embedding/

Query Embedding
rag/retrieval/query_embedding.py
```

Embedding dimension을 변경하면 DB Schema와 Runtime Retrieval도 함께 확인해야 합니다.

---

## 14. Retrieval Architecture

현재 Runtime Retrieval은:

```text
PostgreSQL + pgvector
```

입니다.

검색 조건에는 선택된 공고가 포함됩니다.

개념:

```text
announcement_id
        +
query_vector
        ↓
active processing run
        ↓
active chunk set
        ↓
completed chunks
        ↓
completed embeddings
        ↓
pgvector cosine similarity
        ↓
Top-K
```

즉 다른 공고의 Chunk가 섞이지 않도록 선택 Announcement 범위에서 검색합니다.

---

## 15. 현재 사용하지 않는 RAG 구조

현재 Runtime 경로에서는 다음 구조를 사용하지 않습니다.

```text
BM25
File-based Corpus Retrieval
Hybrid Search
Separate Reranker Model
```

따라서 현재 Runtime RAG를 설명할 때:

```text
Hybrid Search → Reranker → Generation
```

이라고 설명하면 안 됩니다.

현재 정확한 흐름:

```text
BGE-M3 Query Embedding
    ↓
PostgreSQL + pgvector Retrieval
    ↓
Generation
```

---

## 16. Generation Architecture

경로:

```text
rag/generation/
```

연결:

```text
Retrieved Results
    ↓
context_builder.py
    ↓
Source Context
    ↓
prompt_builder.py
    ↓
Prompt
    ↓
llm_client.py
    ↓
LLM Response
    ↓
generator.py
    ↓
GeneratedAnswer
```

---

## 17. Generation Failure와 Retrieval Failure 구분

다음과 같은 경우:

```text
HTTP 200
grounded = true
evidence 존재
answer = fallback message
```

이면 대부분:

```text
Backend 연결 실패 X
DB 연결 실패 X
Retrieval 완전 실패 X
Frontend 연결 실패 X
Generation 품질/검증 문제 가능성 높음
```

입니다.

따라서 이 상황에서는 Parser나 Frontend부터 다시 수정하지 않습니다.

우선:

```text
rag/generation/generator.py
rag/generation/prompt_builder.py
rag/generation/context_builder.py
rag/generation/llm_client.py
```

를 확인합니다.

---

## 18. Database Architecture

ORM:

```text
backend/app/models/
```

DB Session:

```text
backend/app/db/session.py
```

Migration:

```text
migrations/
```

Alembic 설정:

```text
alembic.ini
```

Infrastructure:

```text
infra/docker-compose.yml
infra/postgres/init/01-enable-vector.sql
```

---

## 19. Active Dataset / Processing 구조

현재 Retrieval SQL은 단순히 Chunk 전체를 검색하지 않고,
활성 상태의 처리 결과를 기준으로 검색합니다.

개념:

```text
System State
    ↓
Active Collection
    ↓
Announcement
    ↓
Active Processing Run
    ↓
Active Chunk Set
    ↓
Chunks
    ↓
Embeddings
```

이 구조는 문서를 재처리하더라도 이전 처리 결과와 새 처리 결과를 구분하고,
활성화된 데이터만 서비스하기 위한 목적입니다.

---

## 20. Frontend Architecture

```text
frontend/
├── user/
└── admin/
```

### User Frontend

```text
React
TypeScript
Vite
```

### Admin Frontend

```text
HTML
CSS
JavaScript
Python proxy/static server
```

---

## 21. User Frontend API Flow

API Base:

```text
frontend/user/src/config.ts
```

현재:

```typescript
export const API_BASE_URL = "/api";
```

목록:

```text
ListScreen.tsx
    ↓
GET /api/announcements
```

상세:

```text
DetailScreen.tsx
    ↓
GET /api/announcements/{id}
```

Chat:

```text
DetailScreen.tsx
    ↓
POST /api/chat
```

---

## 22. Proxy Architecture

Browser에서 Backend 주소를 하드코딩하지 않습니다.

```text
Browser
    ↓
/api
    ↓
Vite Proxy
    ↓
FastAPI :8000
```

User Frontend의 실제 Proxy 설정은:

```text
frontend/user/vite.config.ts
```

를 확인합니다.

---

## 23. Admin Frontend API Flow

Admin API Base:

```text
/api
```

관련 파일:

```text
frontend/admin/js/config.js
frontend/admin/js/api.js
frontend/admin/serve_admin.py
```

`serve_admin.py`가 Admin UI 정적 파일 제공과 API proxy 역할을 담당합니다.

---

## 24. Module Boundary

프로젝트에서 가장 중요한 원칙은 **단계 사이의 계약을 유지하는 것**입니다.

```text
Parser
  │
  │ Parser Document Contract
  ▼
Normalizer
  │
  │ Normalized Document Contract
  ▼
Structure
  │
  │ Structured Document Contract
  ▼
Chunking
  │
  │ Chunk Contract
  ▼
Embedding
  │
  │ Vector + Metadata Contract
  ▼
Persistence
```

RAG:

```text
Query
  ↓
Retrieval
  │
  │ Retrieval Result Contract
  ▼
Generation
  │
  │ Generated Result
  ▼
RAG Service
  │
  │ Chat Contract
  ▼
Backend
```

---

## 25. 특정 모듈을 교체할 때

### Parser 교체

변경:

```text
pipeline/parser/
```

유지:

```text
Parser output contract
```

가능하면 수정하지 않는 영역:

```text
Normalizer
Structure
Chunking
Embedding
RAG
Frontend
```

---

### Structure 교체

변경:

```text
pipeline/structure/
```

유지:

```text
Chunking 입력 계약
```

---

### Chunking 교체

변경:

```text
pipeline/chunking/
```

유지:

```text
chunk ID
content
search text
section/source metadata
```

영향 가능:

```text
Embedding
Persistence
RAG
```

---

### Embedding 교체

변경:

```text
pipeline/embedding/
rag/retrieval/query_embedding.py
```

반드시 함께 확인:

```text
Embedding dimension
DB vector column
Migration
RAG SQL
```

---

### Retrieval 교체

주요 변경:

```text
rag/db_pipeline.py
rag/retrieval/
```

유지:

```text
Generation이 필요로 하는 Retrieval Result Contract
```

가능하면 수정하지 않음:

```text
Backend API
Frontend
```

---

### Generation 교체

주요 변경:

```text
rag/generation/
```

유지:

```text
Generated answer
sources/evidence
RAG service output contract
```

Backend/Frontend API를 그대로 유지할 수 있습니다.

---

### Backend Service 교체

유지:

```text
HTTP API Contract
```

그러면 Frontend 수정 필요성을 줄일 수 있습니다.

---

## 26. Contract Summary

| 경계 | 입력 | 출력 | 반드시 유지할 의미 |
|---|---|---|---|
| Parser → Normalizer | Parser Document | Normalized Document | 문단/표/source |
| Normalizer → Structure | Normalized Document | Structured Document | 문서 구조 |
| Structure → Chunking | Structured Document | Chunks | Section/Table 의미 |
| Chunking → Embedding | Chunk | Vector Input | Chunk ID/Text |
| Embedding → DB | Vector + Metadata | DB Record | Dimension/Model |
| Query → Retrieval | Question | Search Results | Query Vector |
| Retrieval → Generation | Retrieved Chunks | Context | Content/Score |
| RAG → Backend | RAG Result | ChatResponse | Answer/Evidence |
| Backend → Frontend | JSON | UI State | API Contract |

---

## 27. Source of Truth

문서와 실제 코드가 다를 경우 다음 코드가 최종 기준입니다.

| 영역 | Source of Truth |
|---|---|
| 전체 Pipeline | `run_pipeline.py` |
| 공통 Path | `config/paths.py` |
| Parser | `pipeline/parser/` |
| Normalizer | `pipeline/normalizer/` |
| Structure | `pipeline/structure/` |
| Chunking | `pipeline/chunking/` |
| Embedding | `pipeline/embedding/` |
| RAG Runtime | `rag/` |
| API URL/Method | `backend/app/api/routes/` |
| API Schema | `backend/app/schemas/` |
| DB ORM | `backend/app/models/` |
| DB Migration | `migrations/` |
| Frontend API Base | `frontend/user/src/config.ts` |
| User Frontend | `frontend/user/src/` |
| Admin Frontend | `frontend/admin/` |

---

## 28. 새로운 개발자 또는 AI가 Architecture를 분석하는 순서

```text
1. README.md
2. docs/ARCHITECTURE.md
3. docs/PROJECT_STRUCTURE.md
4. 작업 대상 상세 문서
5. 실제 Source Code
```

특정 코드를 수정하기 전에 반드시:

```text
호출자
입력
출력
다음 단계
영향 범위
```

를 확인합니다.

단순히 파일 이름이 비슷하다는 이유만으로 다른 계층까지 함께 수정하지 않습니다.
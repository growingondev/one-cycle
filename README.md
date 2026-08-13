# DDOKBOT

> 한글 공고문(HWP/HWPX)을 구조화하고 PostgreSQL + pgvector 기반 검색과 LLM을 이용하여  
> 사용자가 특정 공고문에 대해 근거 기반 질의응답을 할 수 있도록 하는 문서 기반 RAG 서비스

---

## 1. 프로젝트 개요

DDOKBOT은 HWP/HWPX 형식의 공고문을 자동으로 처리하여 검색 가능한 데이터로 변환하고,
사용자가 선택한 공고문에 대해 자연어로 질문하면 관련 근거를 검색하여 답변하는 서비스입니다.

프로젝트는 크게 다음 영역으로 구성됩니다.

- **Document Pipeline**: HWP/HWPX 문서를 파싱·정규화·구조화·청킹·임베딩
- **Database**: 처리 결과와 임베딩을 PostgreSQL + pgvector에 저장
- **RAG**: 질문을 임베딩하고 선택 공고에서 관련 Chunk 검색 후 답변 생성
- **Backend**: FastAPI 기반 API 및 서비스 연결
- **User Frontend**: 일반 사용자용 React 웹 UI
- **Admin Frontend**: 공고·문서·처리 상태 등을 관리하는 관리자 UI

---

## 2. 프로젝트 루트

AWS 개발 서버 기준 프로젝트 경로는 다음과 같습니다.

```text
/home/ubuntu/ddokbot/one-cycle
```

이 문서에서 별도 설명이 없는 모든 상대 경로는 위 디렉터리를 기준으로 합니다.

---

## 3. 전체 시스템 구조

```text
                           ┌──────────────────────┐
                           │     User Browser     │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │    User Frontend     │
                           │ React + TS + Vite    │
                           │ frontend/user/       │
                           └──────────┬───────────┘
                                      │
                                    /api
                                      │
                                      ▼
┌───────────────────┐      ┌──────────────────────┐
│  Admin Frontend   │─────▶│       FastAPI        │
│ frontend/admin/   │ /api │ backend/app/main.py  │
└───────────────────┘      └──────────┬───────────┘
                                      │
                     ┌────────────────┴────────────────┐
                     │                                 │
                     ▼                                 ▼
          ┌────────────────────┐           ┌────────────────────┐
          │ Application Service│           │        RAG         │
          │ backend/app/       │           │ rag/               │
          │ services/          │           │                    │
          └─────────┬──────────┘           └─────────┬──────────┘
                    │                                │
                    │                                │
                    ▼                                ▼
          ┌──────────────────────────────────────────────────────┐
          │              PostgreSQL + pgvector                   │
          └──────────────────────▲───────────────────────────────┘
                                 │
                                 │ Persistence
                                 │
                      ┌──────────┴──────────┐
                      │ Document Pipeline  │
                      │ pipeline/          │
                      └─────────────────────┘
```

---

## 4. 문서 처리 전체 흐름

원본 공고문은 다음 순서로 처리됩니다.

```text
HWP / HWPX
    │
    ▼
Parser
pipeline/parser/
    │
    ▼
Parsed JSON
    │
    ▼
Normalizer
pipeline/normalizer/
    │
    ▼
Normalized JSON
    │
    ▼
Structure
pipeline/structure/
    │
    ▼
Structured JSON
    │
    ▼
Chunking
pipeline/chunking/
    │
    ▼
chunks.json
    │
    ▼
Embedding
pipeline/embedding/
    │
    ▼
Embedding + Metadata
    │
    ▼
Persistence
backend/app/services/pipeline_persistence.py
    │
    ▼
PostgreSQL + pgvector
```

전체 Pipeline의 상위 실행 진입점은 다음 파일입니다.

```text
run_pipeline.py
```

---

## 5. Pipeline 실행 코드 연결

`run_pipeline.py`가 각 Pipeline 단계의 실행 파일을 순서대로 호출합니다.

주요 연결 관계는 다음과 같습니다.

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

`run_pipeline.py` 내부에서 관리하는 주요 경로는 다음과 같습니다.

```python
PARSER_DIR = BASE_DIR / "pipeline" / "parser"
NORMALIZER_DIR = BASE_DIR / "pipeline" / "normalizer"
STRUCTURE_DIR = BASE_DIR / "pipeline" / "structure"
CHUNKING_DIR = BASE_DIR / "pipeline" / "chunking"
EMBEDDING_DIR = BASE_DIR / "pipeline" / "embedding"
```

실제 runner 파일:

```python
HWP_PARSER_PATH = PARSER_DIR / "hwp_parser.py"
HWPX_PARSER_PATH = PARSER_DIR / "hwpx_parser.py"

NORMALIZER_PATH = NORMALIZER_DIR / "document_normalizer.py"

STRUCTURE_RUNNER_PATH = STRUCTURE_DIR / "run_structure.py"

CHUNKING_RUNNER_PATH = CHUNKING_DIR / "run_chunking.py"

EMBEDDING_RUNNER_PATH = EMBEDDING_DIR / "run_embeddings.py"
```

따라서 Pipeline 관련 파일을 이동할 경우 `run_pipeline.py`의 경로 정의도 반드시 확인해야 합니다.

---

## 6. Pipeline 실행

프로젝트 루트로 이동합니다.

```bash
cd /home/ubuntu/ddokbot/one-cycle
```

프로젝트 Python 환경을 사용합니다.

현재 개발 환경에서 사용한 Backend 가상환경:

```text
/home/ubuntu/ddokbot/venvs/one-cycle-backend
```

예:

```bash
source /home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/activate
```

전체 Pipeline 실행 진입점:

```bash
python run_pipeline.py
```

Pipeline 실행 과정에서 생성되는 중간/최종 산출물은 기본적으로 다음 위치에서 관리합니다.

```text
outputs/
```

공통 output 경로 관련 코드는 다음 파일에서 관리합니다.

```text
config/paths.py
```

---

## 7. Pipeline 단계별 책임

### 7.1 Parser

경로:

```text
pipeline/parser/
```

주요 파일:

```text
pipeline/parser/hwp_parser.py
pipeline/parser/hwpx_parser.py
pipeline/parser/common.py
pipeline/parser/libs/
```

역할:

```text
HWP/HWPX 원본 문서
        ↓
문단 / 표 / 문서 요소 추출
        ↓
Parser JSON
```

HWP와 HWPX는 서로 다른 Parser를 사용하지만,
후속 Pipeline에서 처리할 수 있는 문서 데이터로 변환하는 동일한 책임을 가집니다.

---

### 7.2 Normalizer

경로:

```text
pipeline/normalizer/document_normalizer.py
```

역할:

```text
Parser JSON
    ↓
표현 및 문자 정규화
    ↓
Normalized JSON
```

주요 처리 대상:

- 텍스트 정규화
- 특수문자 정리
- 제어문자 처리
- 측정 단위 표현 정리
- 표 및 셀 정보 정규화
- 검색용 텍스트 생성
- source 정보 정규화

Parser 구현을 변경하더라도 Normalizer가 기대하는 입력 계약을 유지하는 것이 중요합니다.

---

### 7.3 Structure

경로:

```text
pipeline/structure/
```

주요 파일:

```text
build_document_step1.py
build_domain_step2.py
build_table_step3.py
finalize_structure.py
run_structure.py
value_normalizer.py
verification.py
domain_rules.json
```

역할:

```text
Normalized JSON
      ↓
문서 논리 구조 분석
      ↓
Section / Domain / Table 구조 생성
      ↓
Structured JSON
```

Structure Pipeline 실행 진입점:

```text
pipeline/structure/run_structure.py
```

---

### 7.4 Chunking

경로:

```text
pipeline/chunking/
```

주요 파일:

```text
chunker.py
config.py
models.py
paragraph_chunker.py
run_chunking.py
section_walker.py
table_chunker.py
text_builder.py
tokenizer.py
validator.py
```

역할:

```text
Structured Document
        ↓
Section 탐색
        ↓
Paragraph / Table Chunk 생성
        ↓
chunks.json
```

Chunk는 이후 Embedding 및 RAG Retrieval의 기본 검색 단위입니다.

따라서 Chunk ID, content, section 정보 등의 변경은 RAG와 DB 저장 구조에 영향을 줄 수 있습니다.

---

### 7.5 Embedding

경로:

```text
pipeline/embedding/
```

주요 파일:

```text
config.py
embedding_generator.py
input_loader.py
model_loader.py
models.py
output_writer.py
run_embeddings.py
validator.py
```

현재 Embedding 모델:

```text
BAAI BGE-M3
```

역할:

```text
chunks.json
    ↓
BGE-M3
    ↓
Dense Embedding
    ↓
Embedding Metadata
```

생성된 Embedding은 이후 PostgreSQL + pgvector 검색에 사용됩니다.

---

## 8. Pipeline → Database 연결

Pipeline 결과의 DB 저장 관련 서비스는 다음 위치에 있습니다.

```text
backend/app/services/pipeline_persistence.py
```

전체 관계:

```text
Pipeline
   ↓
outputs/
   ↓
pipeline_persistence.py
   ↓
SQLAlchemy
   ↓
PostgreSQL
   ↓
pgvector
```

DB ORM 모델은 다음 위치에서 관리합니다.

```text
backend/app/models/
```

주요 모델 영역:

```text
announcement.py
document.py
document_structure.py
chunk.py
chunk_set.py
embedding.py
key_information.py
processing_run.py
processing_artifact.py
collection_run.py
system_state.py
admin.py
error_log.py
```

---

## 9. Database

DDOKBOT은 다음 DB를 사용합니다.

```text
PostgreSQL
+
pgvector
```

관련 Infrastructure:

```text
infra/docker-compose.yml
infra/postgres/init/01-enable-vector.sql
```

SQLAlchemy 설정:

```text
backend/app/db/
├── base.py
└── session.py
```

DB Schema 변경은 Alembic으로 관리합니다.

```text
alembic.ini
migrations/
```

Migration 적용:

```bash
cd /home/ubuntu/ddokbot/one-cycle
alembic upgrade head
```

> `alembic.ini`는 DB 내부 파일이 아닙니다.
> Alembic CLI가 프로젝트의 Migration 환경을 찾고 실행하기 위한 프로젝트 단위 설정 파일이므로 프로젝트 루트에 위치합니다.

---

## 10. RAG 전체 흐름

현재 실제 서비스 RAG는 PostgreSQL + pgvector 기반입니다.

```text
사용자 질문
    │
    ▼
POST /api/chat
    │
    ▼
backend/app/api/routes/chat.py
    │
    ▼
backend/app/services/chat_service.py
    │
    ▼
rag.service:answer_question
    │
    ▼
rag/service.py
    │
    ▼
rag/db_pipeline.py
    │
    ├── Query Embedding
    │       │
    │       ▼
    │   rag/retrieval/query_embedding.py
    │
    ├── PostgreSQL + pgvector Retrieval
    │
    ▼
관련 Chunk
    │
    ▼
rag/generation/
    │
    ├── context_builder.py
    ├── prompt_builder.py
    ├── generator.py
    └── llm_client.py
    │
    ▼
Answer + Evidence
    │
    ▼
FastAPI
    │
    ▼
User Frontend
```

---

## 11. RAG Backend 연결

Chat API Route:

```text
backend/app/api/routes/chat.py
```

Chat Application Service:

```text
backend/app/services/chat_service.py
```

RAG 진입 함수는 환경변수를 통해 연결할 수 있습니다.

```text
RAG_ANSWER_FUNCTION
```

현재 RAG 구현의 진입점:

```text
rag.service:answer_question
```

따라서 연결 구조는 다음과 같습니다.

```text
chat.py
  ↓
chat_service.py
  ↓
RAG_ANSWER_FUNCTION
  ↓
rag.service:answer_question
```

이 구조 덕분에 Backend API 자체를 크게 수정하지 않고 RAG 구현을 교체할 수 있습니다.

---

## 12. Query Embedding

현재 질문 Embedding 관련 코드는 다음 위치에 있습니다.

```text
rag/retrieval/query_embedding.py
```

흐름:

```text
사용자 질문
    ↓
BGE-M3 encode()
    ↓
Dense Vector
    ↓
Normalization
    ↓
pgvector 검색 Query
```

Embedding model loader는 Pipeline과 공통으로 다음 구현을 사용합니다.

```text
pipeline/embedding/model_loader.py
```

---

## 13. Retrieval

현재 Runtime Retrieval은 DB 기반입니다.

핵심 코드:

```text
rag/db_pipeline.py
```

검색 흐름:

```text
announcement_id
      +
question embedding
      ↓
PostgreSQL
      ↓
pgvector similarity search
      ↓
선택 공고에 속하는 관련 Chunk
      ↓
Top-K 결과
```

현재 실제 서비스 Runtime 경로에서는 다음 방식을 사용하지 않습니다.

- 파일 기반 전체 Corpus 검색
- BM25 Hybrid Search
- 별도 Reranker 모델 실행

과거 관련 구현은 프로젝트 정리 과정에서 제거되었습니다.

---

## 14. Generation

경로:

```text
rag/generation/
```

구조:

```text
rag/generation/
├── __init__.py
├── config.py
├── context_builder.py
├── generator.py
├── llm_client.py
├── models.py
└── prompt_builder.py
```

역할:

```text
Retrieval Results
       ↓
context_builder.py
       ↓
Generation Context
       ↓
prompt_builder.py
       ↓
Prompt
       ↓
llm_client.py
       ↓
LLM
       ↓
generator.py
       ↓
Generated Answer
```

현재 프로젝트에서 개선이 가장 필요한 부분 중 하나입니다.

Retrieval에서 올바른 근거를 찾았음에도 Generation이 안정적인 답변을 만들지 못하는 경우가 확인되었습니다.

예를 들어 검색 결과에 실제 신청 일정이 존재하더라도 최종 응답이 다음과 같이 fallback될 수 있습니다.

```text
공고문 근거는 확인되었지만 현재 답변 생성 품질이 안정적이지 않아
정확한 문장으로 제공하지 못했습니다.
```

따라서 Retrieval과 Generation 문제를 구분해서 디버깅해야 합니다.

---

## 15. RAG 응답 계약

Chat API 요청 예:

```json
{
  "announcementId": 1,
  "question": "신청 일정은 언제인가?"
}
```

응답의 주요 형태:

```json
{
  "answer": "답변 문자열",
  "grounded": true,
  "evidence": [
    {
      "chunkId": "chunk-id",
      "sectionTitle": "section",
      "content": "근거 내용",
      "score": 0.58
    }
  ]
}
```

즉 Frontend는 RAG 내부 구현을 알 필요가 없으며 다음 API 계약만 사용합니다.

```text
POST /api/chat
        ↓
answer
grounded
evidence
```

---

## 16. Backend

Backend 기술:

```text
FastAPI
SQLAlchemy
Pydantic
PostgreSQL
pgvector
Alembic
```

Application 진입점:

```text
backend/app/main.py
```

주요 구조:

```text
backend/app/
├── api/
│   ├── dependencies.py
│   ├── router.py
│   └── routes/
│
├── core/
│   └── config.py
│
├── db/
│   ├── base.py
│   └── session.py
│
├── models/
├── schemas/
├── services/
└── main.py
```

---

## 17. Backend 계층 관계

```text
HTTP Request
     ↓
API Route
backend/app/api/routes/
     ↓
Pydantic Schema
backend/app/schemas/
     ↓
Application Service
backend/app/services/
     ↓
SQLAlchemy / RAG / Pipeline
     ↓
Response
```

Route에서 복잡한 비즈니스 로직을 직접 처리하지 않고 Service 계층을 통해 기능을 연결하는 것을 기본 원칙으로 합니다.

---

## 18. 주요 API

Frontend 기준 API Base Path:

```text
/api
```

### Health

```text
GET /api/health
GET /api/health/db
```

### Announcements

```text
GET /api/announcements
GET /api/announcements/{id}
```

### Chat

```text
POST /api/chat
```

### Admin

관리자 API는 다음 코드에서 관리합니다.

```text
backend/app/api/routes/admin.py
backend/app/api/routes/admin_auth.py
```

API 문서와 코드가 다를 경우 **실제 Route와 Schema 코드가 최종 기준(Source of Truth)** 입니다.

```text
backend/app/api/routes/
backend/app/schemas/
```

---

## 19. User Frontend

경로:

```text
frontend/user/
```

기술:

```text
React
TypeScript
Vite
```

주요 화면:

```text
frontend/user/src/components/screens/
```

공고 목록:

```text
ListScreen.tsx
```

공고 상세 및 Chat:

```text
DetailScreen.tsx
```

Frontend API 설정:

```text
frontend/user/src/config.ts
```

현재 설정:

```typescript
export const API_BASE_URL = "/api";
```

API 주소는 위 파일에서 단일 관리합니다.

---

## 20. User Frontend → Backend 연결

공고 목록:

```text
ListScreen.tsx
    ↓
GET /api/announcements
    ↓
FastAPI
```

공고 상세:

```text
DetailScreen.tsx
    ↓
GET /api/announcements/{id}
    ↓
FastAPI
```

Chat:

```text
DetailScreen.tsx
    ↓
POST /api/chat
    ↓
FastAPI
    ↓
RAG
```

Vite 개발 환경에서는 `/api` 요청을 Backend로 Proxy합니다.

따라서 Browser 코드에 AWS Backend IP나 `127.0.0.1:8000`을 직접 넣지 않습니다.

---

## 21. User Frontend 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm install
npm run dev
```

Production Build 확인:

```bash
npm run build
```

현재 정리된 코드 기준으로 Production Build 성공을 확인한 상태입니다.

---

## 22. Admin Frontend

경로:

```text
frontend/admin/
```

구성:

```text
HTML
CSS
JavaScript
Python static/proxy server
```

주요 파일:

```text
announcement.html
document.html
error.html
login.html

components/
css/
js/

serve_admin.py
```

Admin Frontend도 API 요청 시 `/api`를 사용합니다.

---

## 23. 프로젝트 디렉터리 구조

```text
one-cycle/
│
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── db/
│       ├── models/
│       ├── schemas/
│       ├── services/
│       └── main.py
│
├── config/
│   └── paths.py
│
├── crawler/
│   └── __init__.py
│
├── docs/
│
├── frontend/
│   ├── admin/
│   └── user/
│
├── infra/
│   ├── docker-compose.yml
│   └── postgres/
│
├── migrations/
│   ├── env.py
│   └── versions/
│
├── outputs/
│
├── pipeline/
│   ├── parser/
│   ├── normalizer/
│   ├── structure/
│   ├── chunking/
│   └── embedding/
│
├── rag/
│   ├── generation/
│   ├── retrieval/
│   ├── db_pipeline.py
│   ├── models.py
│   └── service.py
│
├── tests/
│   └── fixtures/
│       └── documents/
│
├── .env
├── .env.example
├── alembic.ini
├── requirements.txt
├── run_pipeline.py
└── README.md
```

---

## 24. 파일을 어디에 추가해야 하는가

새 기능을 추가할 때 다음 기준을 사용합니다.

| 추가하려는 기능 | 위치 |
|---|---|
| 새로운 API Endpoint | `backend/app/api/routes/` |
| API Request/Response Schema | `backend/app/schemas/` |
| Backend 비즈니스 로직 | `backend/app/services/` |
| 새로운 DB Table | `backend/app/models/` |
| DB Schema Migration | `migrations/versions/` |
| HWP/HWPX Parsing | `pipeline/parser/` |
| 문서 정규화 | `pipeline/normalizer/` |
| 문서 구조 분석 | `pipeline/structure/` |
| Chunk 생성 | `pipeline/chunking/` |
| Embedding 생성 | `pipeline/embedding/` |
| 질문 Embedding/Retrieval | `rag/retrieval/` |
| DB 기반 RAG orchestration | `rag/db_pipeline.py` |
| Prompt/LLM 답변 생성 | `rag/generation/` |
| RAG 외부 진입점 | `rag/service.py` |
| 사용자 UI | `frontend/user/` |
| 관리자 UI | `frontend/admin/` |
| 공통 경로 설정 | `config/paths.py` |
| DB/Postgres Infrastructure | `infra/` |
| 검증용 원본 문서 | `tests/fixtures/documents/` |
| 실행 산출물 | `outputs/` |
| 프로젝트 문서 | `docs/` |

---

## 25. 모듈 교체 시 지켜야 할 경계

DDOKBOT은 특정 파트를 수정할 때 전체 프로젝트를 다시 수정하지 않도록 계층 간 계약을 유지하는 것을 원칙으로 합니다.

### Parser 교체

```text
Parser 구현 변경
      ↓
Parser 출력 계약 유지
      ↓
Normalizer 이하 변경 최소화
```

### Normalizer 교체

```text
Normalizer 구현 변경
      ↓
Structured Pipeline이 요구하는 데이터 유지
      ↓
Structure 이하 변경 최소화
```

### Chunking 교체

```text
Chunking 구현 변경
      ↓
Chunk ID / Content / Metadata 계약 유지
      ↓
Embedding / DB / RAG 변경 최소화
```

### Retrieval 교체

```text
Retrieval 구현 변경
      ↓
Generation에 전달하는 검색 결과 계약 유지
      ↓
Generation / Backend 변경 최소화
```

### Generation 교체

```text
LLM / Prompt / Generator 변경
      ↓
RAG Service 반환 계약 유지
      ↓
Backend / Frontend 변경 불필요
```

### Backend 내부 구현 변경

```text
Backend Service 변경
      ↓
HTTP API Schema 유지
      ↓
Frontend 변경 불필요
```

---

## 26. 주요 계층 계약

| 경계 | 입력 | 출력 | 변경 시 유지할 것 |
|---|---|---|---|
| Parser → Normalizer | Parser JSON | Normalized Document | Parser 문서 구조 |
| Normalizer → Structure | Normalized JSON | Structured Document | 문단/표/source 정보 |
| Structure → Chunking | Structured Document | Chunk Collection | Section/Table 구조 |
| Chunking → Embedding | Chunk Collection | Vector + Metadata | Chunk ID와 Text |
| Pipeline → DB | Pipeline Outputs | DB Records | Persistence Schema |
| Query → Retrieval | Question | Search Results | Query Embedding 차원 |
| Retrieval → Generation | Retrieved Chunks | Context | Chunk/content/score |
| RAG → Backend | RAG Result | ChatResponse | answer/grounded/evidence |
| Backend → Frontend | HTTP JSON | UI State | API Contract |

---

## 27. 환경 변수

실제 환경 설정:

```text
.env
```

예제:

```text
.env.example
```

현재 코드에서 사용되는 주요 환경변수 영역:

```text
Database
RAG
Admin Authentication
Pipeline Gateway
```

확인된 주요 환경변수 예:

```text
RAG_ANSWER_FUNCTION

ADMIN_ID
ADMIN_PASSWORD
ADMIN_JWT_SECRET
ADMIN_JWT_EXPIRE_SECONDS
ADMIN_COOKIE_SECURE
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SAMESITE
```

실제 비밀번호나 Secret 값은 README 또는 Source Code에 기록하지 않습니다.

---

## 28. 개발 환경 실행 순서

일반적인 개발 순서는 다음과 같습니다.

### 1. 프로젝트 이동

```bash
cd /home/ubuntu/ddokbot/one-cycle
```

### 2. Python 환경 활성화

```bash
source /home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/activate
```

### 3. PostgreSQL 확인

PostgreSQL 및 pgvector 환경이 실행되어 있어야 합니다.

### 4. Migration 적용

```bash
alembic upgrade head
```

### 5. Backend 실행

```bash
uvicorn backend.app.main:app \
  --host 127.0.0.1 \
  --port 8000
```

### 6. User Frontend 실행

별도 Terminal:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user
npm run dev
```

### 7. 필요 시 Pipeline 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle
python run_pipeline.py
```

---

## 29. 로컬에서 AWS Frontend 확인

AWS의 Vite Server를 로컬 브라우저에서 확인하려면 SSH Port Forwarding을 사용할 수 있습니다.

로컬 Mac 등의 Terminal에서:

```bash
ssh -i <PEM_FILE_PATH> \
  -L 5173:127.0.0.1:5173 \
  ubuntu@<AWS_SERVER_IP>
```

그 후 로컬 Browser에서 Vite Frontend에 접근합니다.

Frontend가 `/api` Proxy를 사용하도록 구성되어 있다면 Browser에서 Backend 주소를 직접 호출하지 않고 Vite가 Backend 요청을 전달합니다.

---

## 30. 코드 검증

### Frontend

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user
npm run build
```

현재 정리 이후 다음 검증을 통과했습니다.

```text
Vite production build 성공
```

### Python

프로젝트 루트에서:

```bash
python -m compileall -q \
  backend \
  config \
  pipeline \
  rag \
  migrations \
  run_pipeline.py
```

현재 정리 이후 Python compile/import 검증을 통과한 상태입니다.

---

## 31. 테스트 문서

Pipeline 검증용 실제 HWP/HWPX 문서는 다음 위치에 둡니다.

```text
tests/fixtures/documents/
```

현재 구조:

```text
tests/fixtures/documents/
├── announcement_001/
├── announcement_002/
├── announcement_003/
└── announcement_004/
```

테스트용 원본 문서는 Pipeline 재현 및 Regression 검증을 위해 사용합니다.

---

## 32. 현재 구현 상태

### 구현 및 연결 확인

- HWP Parser
- HWPX Parser
- Normalizer
- Structure Pipeline
- Chunking
- BGE-M3 Embedding
- Pipeline Persistence
- PostgreSQL
- pgvector
- Announcement API
- Chat API
- User Frontend
- Admin Frontend
- Frontend ↔ Backend 연결
- RAG Retrieval
- RAG Evidence 반환

### 추가 개선 필요

- Generation 답변 품질
- Prompt 안정화
- Generation 실패 처리
- RAG 품질 평가
- Key Information 관련 기능 검증/보완
- Crawler 구현

### 현재 사용하지 않는 구조

현재 Runtime RAG에서는 다음 구조를 사용하지 않습니다.

- BM25 검색
- 파일 기반 Hybrid Search
- 별도 Reranker Model

---

## 33. 현재 가장 중요한 RAG 문제

현재 확인된 Chat API 상태에서는 Retrieval 자체는 관련 Chunk를 찾을 수 있습니다.

예를 들어 사용자가:

```text
신청 일정은 언제인가?
```

라고 질문했을 때 관련 공고에서 다음과 같은 일정 Chunk가 검색될 수 있습니다.

```text
'26.07.23.(목) 오전 10시 ~ 별도 공지시까지
```

즉:

```text
Question Embedding
        ↓
pgvector Retrieval
        ↓
Evidence 검색
```

까지는 동작할 수 있습니다.

하지만 이후:

```text
Evidence
   ↓
Context
   ↓
Prompt
   ↓
LLM
```

구간에서 답변 생성 품질이 안정적이지 않은 문제가 남아 있습니다.

따라서 Chat 품질 문제를 분석할 때 Retrieval과 Generation을 구분해야 합니다.

---

## 34. Source of Truth

문서와 실제 구현이 충돌할 경우 다음 순서로 실제 코드를 기준으로 판단합니다.

| 영역 | 최종 기준 |
|---|---|
| API URL / Method | `backend/app/api/routes/` |
| API Request/Response | `backend/app/schemas/` |
| DB Schema | `backend/app/models/` + `migrations/` |
| Backend Logic | `backend/app/services/` |
| Pipeline | `pipeline/` + `run_pipeline.py` |
| Output Path | `config/paths.py` |
| RAG | `rag/` |
| User API Base URL | `frontend/user/src/config.ts` |
| User UI | `frontend/user/src/` |
| Admin UI | `frontend/admin/` |
| Infrastructure | `infra/` |

---

## 35. 다른 개발자 또는 AI에게 프로젝트를 넘길 때

새로운 개발자 또는 ChatGPT가 프로젝트를 처음 분석하는 경우 다음 순서로 확인하는 것을 권장합니다.

```text
1. README.md
       ↓
2. docs/ARCHITECTURE.md
       ↓
3. docs/PROJECT_STRUCTURE.md
       ↓
4. 수정하려는 영역의 상세 문서
       ↓
5. 실제 Source Code
```

다음 파일을 함께 제공하면 프로젝트 전체 구조를 빠르게 파악할 수 있습니다.

```text
README.md

docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/PIPELINE.md
docs/RAG.md
docs/BACKEND.md
docs/FRONTEND.md
docs/API.md
docs/DEVELOPMENT.md
```

---

## 36. AI 작업 인수인계 요약

다른 AI가 이 프로젝트를 수정해야 할 경우 다음 내용을 우선 이해해야 합니다.

```text
PROJECT
DDOKBOT

PROJECT ROOT
/home/ubuntu/ddokbot/one-cycle

BACKEND
FastAPI

BACKEND ENTRY
backend.app.main:app

BACKEND DEVELOPMENT PORT
8000

USER FRONTEND
frontend/user/

USER FRONTEND
React + TypeScript + Vite

FRONTEND API BASE
/api

PIPELINE ENTRY
run_pipeline.py

PIPELINE
Parser
→ Normalizer
→ Structure
→ Chunking
→ Embedding
→ Persistence

DATABASE
PostgreSQL + pgvector

QUERY EMBEDDING
BGE-M3

RAG ENTRY
rag.service:answer_question

RAG
Question
→ BGE-M3 Query Embedding
→ PostgreSQL/pgvector
→ Relevant Chunks
→ Generation
→ Answer + Evidence

CURRENT RETRIEVAL
DB + pgvector

CURRENT RERANKER
Not used

CURRENT MAJOR ISSUE
Generation quality is unstable even when correct evidence is retrieved.

CRAWLER
Not implemented yet.
```

AI는 특정 기능을 수정하기 전에 반드시 해당 기능의 **입력/출력 계약과 호출자를 먼저 확인**해야 합니다.

기존 계약을 유지할 수 있다면 다른 계층을 불필요하게 수정하지 않습니다.

---

## 37. 상세 문서

프로젝트의 세부 사항은 다음 문서를 기준으로 합니다.

- [Architecture](docs/ARCHITECTURE.md)
- [Project Structure](docs/PROJECT_STRUCTURE.md)
- [Pipeline](docs/PIPELINE.md)
- [RAG](docs/RAG.md)
- [Backend](docs/BACKEND.md)
- [Frontend](docs/FRONTEND.md)
- [API](docs/API.md)
- [Development](docs/DEVELOPMENT.md)

---

## 38. 문서 관리 원칙

이 README와 `docs/` 아래 문서는 현재 프로젝트의 공식 개발 문서입니다.

프로젝트 구조가 변경될 경우 코드만 수정하고 끝내지 않고 관련 문서도 함께 수정합니다.

특히 다음 변경은 반드시 문서에 반영합니다.

- 파일 또는 디렉터리 이동
- Pipeline 단계 변경
- Pipeline 입력/출력 변경
- DB Schema 변경
- API Contract 변경
- RAG Retrieval 변경
- LLM 또는 Generation 구조 변경
- Frontend ↔ Backend 연결 방식 변경
- 실행 명령 또는 Port 변경

문서와 코드가 일치하도록 유지하는 것을 프로젝트 관리 원칙으로 합니다.
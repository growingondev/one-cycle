# DDOKBOT Project Structure

> 이 문서는 DDOKBOT 프로젝트의 실제 디렉터리와 주요 파일의 역할을 설명합니다.
>
> 개발자 또는 AI가 프로젝트를 처음 확인했을 때  
> **“어떤 기능을 수정하려면 어느 파일을 봐야 하는가?”**를 빠르게 판단하기 위한 문서입니다.
>
> 전체 시스템의 데이터 흐름과 계층 구조는 `docs/ARCHITECTURE.md`를 먼저 참고합니다.

---

# 1. Project Root

프로젝트 Root:

```text
/home/ubuntu/ddokbot/one-cycle
```

현재 주요 구조:

```text
one-cycle/
├── .env
├── .env.example
├── alembic.ini
│
├── backend/
├── config/
├── crawler/
├── docs/
├── frontend/
├── infra/
├── migrations/
├── outputs/
├── pipeline/
├── rag/
├── tests/
│
├── requirements.txt
└── run_pipeline.py
```

각 디렉터리의 책임:

| 경로 | 역할 |
|---|---|
| `backend/` | FastAPI API 및 Application Service |
| `config/` | 프로젝트 공통 경로 설정 |
| `crawler/` | 향후 공고 수집 기능 영역 |
| `docs/` | 프로젝트 공식 문서 |
| `frontend/` | 사용자/관리자 UI |
| `infra/` | PostgreSQL/pgvector 실행 환경 |
| `migrations/` | Alembic DB Migration |
| `outputs/` | Pipeline 중간 및 최종 산출물 |
| `pipeline/` | 문서 처리 Pipeline |
| `rag/` | 검색 및 답변 생성 Runtime |
| `tests/` | Pipeline 검증용 테스트 문서 |
| `run_pipeline.py` | 전체 문서 Pipeline 실행 진입점 |

---

# 2. 가장 먼저 봐야 하는 파일

프로젝트를 처음 분석할 경우 다음 순서로 확인합니다.

```text
README.md
    ↓
docs/ARCHITECTURE.md
    ↓
docs/PROJECT_STRUCTURE.md
    ↓
run_pipeline.py
    ↓
backend/app/main.py
    ↓
rag/service.py
    ↓
rag/db_pipeline.py
```

Frontend 문제라면 추가로:

```text
frontend/user/src/config.ts
frontend/user/src/components/screens/
frontend/user/vite.config.ts
```

를 확인합니다.

---

# 3. run_pipeline.py

경로:

```text
/run_pipeline.py
```

역할:

**전체 문서 처리 Pipeline의 Orchestrator**

이 파일이 각 Pipeline 단계를 순서대로 실행합니다.

연결:

```text
run_pipeline.py
    │
    ├── Parser
    ├── Normalizer
    ├── Structure
    ├── Chunking
    ├── Embedding
    └── Persistence
```

주요 연결 경로:

```text
pipeline/parser/hwp_parser.py
pipeline/parser/hwpx_parser.py
pipeline/normalizer/document_normalizer.py
pipeline/structure/run_structure.py
pipeline/chunking/run_chunking.py
pipeline/embedding/run_embeddings.py
backend/app/services/pipeline_persistence.py
```

이 파일을 수정해야 하는 경우:

- Pipeline 단계 순서를 변경할 때
- 새로운 Pipeline 단계를 추가할 때
- Pipeline 실행 방식을 변경할 때
- Stage 간 파일 전달 방식을 변경할 때

개별 Parser나 Chunking 알고리즘만 수정하려는 경우에는 이 파일을 먼저 수정하지 않습니다.

---

# 4. config/

구조:

```text
config/
└── paths.py
```

## config/paths.py

프로젝트 전체에서 사용하는 공통 Path 정의를 담당합니다.

대표적으로:

```text
outputs/
tests/fixtures/
문서별 output directory
```

등의 경로 계산을 담당합니다.

Path 관련 문제가 발생하면 여러 파일에 경로를 하드코딩하기 전에 이 파일을 먼저 확인합니다.

예:

```text
Pipeline output 위치 변경
문서별 output 구조 변경
test fixture 위치 변경
```

---

# 5. pipeline/

전체 문서 처리 코드입니다.

```text
pipeline/
├── parser/
├── normalizer/
├── structure/
├── chunking/
└── embedding/
```

전체 처리 순서:

```text
Parser
  ↓
Normalizer
  ↓
Structure
  ↓
Chunking
  ↓
Embedding
```

---

# 6. pipeline/parser/

구조:

```text
pipeline/parser/
├── __init__.py
├── common.py
├── hwp_parser.py
├── hwpx_parser.py
└── libs/
    ├── hwp/
    └── hwpx/
```

---

## hwp_parser.py

역할:

```text
HWP
 ↓
Parser JSON
```

HWP 문서를 읽어 Paragraph/Table 등의 구조를 추출합니다.

관련 외부 Library는:

```text
pipeline/parser/libs/hwp/
```

에 위치합니다.

---

## hwpx_parser.py

역할:

```text
HWPX
 ↓
Parser JSON
```

HWPX 문서를 처리합니다.

관련 Library:

```text
pipeline/parser/libs/hwpx/
```

---

## common.py

HWP/HWPX Parser에서 공통으로 사용하는 기능을 담당합니다.

Parser 공통 환경 설정이나 Library 경로 처리 등을 확인할 때 봅니다.

---

# 7. pipeline/normalizer/

구조:

```text
pipeline/normalizer/
└── document_normalizer.py
```

## document_normalizer.py

역할:

```text
Parser JSON
    ↓
Normalized JSON
```

Parser마다 조금씩 달라질 수 있는 데이터를 이후 Pipeline에서 사용하기 쉬운 형태로 정규화합니다.

주요 책임:

```text
문자 정규화
특수문자 처리
단위 표현 정리
Paragraph 정규화
Table/Cell 정규화
Source 정보 정리
Search Text 생성
```

수정 시 영향:

```text
Structure
Chunking
Embedding
RAG 검색 품질
```

Normalizer output contract를 변경하면 후속 단계 전체를 확인해야 합니다.

---

# 8. pipeline/structure/

구조:

```text
pipeline/structure/
├── __init__.py
├── build_document_step1.py
├── build_domain_step2.py
├── build_table_step3.py
├── domain_rules.json
├── finalize_structure.py
├── run_structure.py
├── value_normalizer.py
└── verification.py
```

---

## run_structure.py

Structure Pipeline의 실행 진입점입니다.

```text
Normalized JSON
      ↓
run_structure.py
      ↓
Structured Document
```

내부적으로 여러 Step을 순차 실행합니다.

---

## build_document_step1.py

문서의 기본 구조를 생성하는 1단계입니다.

---

## build_domain_step2.py

공고문 Domain 정보를 구조화하는 단계입니다.

예를 들어 공고문의 의미 있는 Section과 Domain 데이터를 구성하는 로직이 이 영역에 위치합니다.

---

## build_table_step3.py

Table 정보를 후속 처리하기 쉬운 구조로 만드는 단계입니다.

공고문은 일정, 공급정보, 소득기준 등의 핵심 정보가 표에 존재하는 경우가 많기 때문에 중요한 단계입니다.

---

## domain_rules.json

Structure 단계에서 사용하는 Domain Rule 정의입니다.

공고문 구조화 규칙을 변경할 때 함께 확인합니다.

---

## finalize_structure.py

여러 Structure Step의 결과를 최종 문서 구조로 정리합니다.

---

## value_normalizer.py

Structure 단계에서 추출한 값의 표현을 정규화합니다.

---

## verification.py

Structure 결과 검증을 담당합니다.

---

# 9. pipeline/chunking/

구조:

```text
pipeline/chunking/
├── __init__.py
├── chunker.py
├── config.py
├── models.py
├── paragraph_chunker.py
├── run_chunking.py
├── section_walker.py
├── table_chunker.py
├── text_builder.py
├── tokenizer.py
└── validator.py
```

---

## run_chunking.py

Chunking 실행 진입점입니다.

```text
Structured Document
        ↓
run_chunking.py
        ↓
chunks.json
```

`run_pipeline.py`에서 호출합니다.

---

## chunker.py

전체 Chunk 생성 로직을 조정합니다.

---

## section_walker.py

Structured Document의 Section 구조를 순회합니다.

---

## paragraph_chunker.py

Paragraph 기반 Chunk 생성 로직입니다.

---

## table_chunker.py

Table 기반 Chunk 생성 로직입니다.

공고문 질의응답에서 일정/소득/공급정보 등의 Table 검색 품질과 직접 연결될 수 있습니다.

---

## text_builder.py

Chunk에 저장될 검색용 Text 및 Content 구성을 담당합니다.

---

## tokenizer.py

Chunk 크기 계산 등에 사용하는 Token 처리 기능입니다.

주의:

```text
pipeline/chunking/tokenizer.py
```

는 현재 Chunking에서 실제 사용되므로 삭제하면 안 됩니다.

---

## config.py

Chunk 크기 등 Chunking 관련 설정입니다.

---

## models.py

Chunking 내부 데이터 구조입니다.

---

## validator.py

생성된 Chunk 결과를 검증합니다.

---

# 10. pipeline/embedding/

구조:

```text
pipeline/embedding/
├── __init__.py
├── config.py
├── embedding_generator.py
├── input_loader.py
├── model_loader.py
├── models.py
├── output_writer.py
├── run_embeddings.py
└── validator.py
```

---

## run_embeddings.py

Embedding Pipeline 실행 진입점입니다.

```text
chunks.json
    ↓
run_embeddings.py
    ↓
Embedding
```

---

## model_loader.py

Embedding Model을 로딩합니다.

현재 RAG Query Embedding에서도 이 Model Loader를 재사용합니다.

연결:

```text
pipeline/embedding/model_loader.py
            ↑
            │
rag/retrieval/query_embedding.py
```

따라서 이 파일 변경은 Offline Embedding뿐 아니라 Runtime 질문 Embedding에도 영향을 줄 수 있습니다.

---

## embedding_generator.py

Chunk Text를 실제 Vector로 변환합니다.

---

## input_loader.py

Chunking 결과를 Embedding 입력으로 읽습니다.

---

## output_writer.py

Embedding 결과와 Metadata를 output에 기록합니다.

---

## models.py

Embedding Pipeline 내부 데이터 모델입니다.

---

## validator.py

Embedding 결과를 검증합니다.

---

# 11. backend/

구조:

```text
backend/
└── app/
    ├── api/
    ├── core/
    ├── db/
    ├── models/
    ├── schemas/
    ├── services/
    └── main.py
```

Backend는 FastAPI 기반입니다.

---

# 12. backend/app/main.py

FastAPI Application 진입점입니다.

Backend 실행 문제 발생 시 가장 먼저 확인하는 파일 중 하나입니다.

역할:

```text
FastAPI App 생성
    ↓
API Router 연결
    ↓
Application 실행
```

---

# 13. backend/app/api/

구조:

```text
backend/app/api/
├── dependencies.py
├── router.py
└── routes/
```

---

## router.py

각 Route를 하나의 API Router로 연결합니다.

---

## dependencies.py

FastAPI Dependency를 정의합니다.

DB Session이나 인증 관련 Dependency가 필요한 경우 이 계층을 확인합니다.

---

# 14. backend/app/api/routes/

현재 주요 Route:

```text
admin.py
admin_auth.py
announcements.py
chat.py
health.py
```

---

## health.py

Backend 및 DB 상태 확인 API입니다.

대표적으로:

```text
/api/health
/api/health/db
```

Backend 문제를 진단할 때 우선 확인합니다.

---

## announcements.py

사용자 공고 목록/상세 API입니다.

Frontend 연결:

```text
ListScreen.tsx
    ↓
GET /api/announcements
```

```text
DetailScreen.tsx
    ↓
GET /api/announcements/{id}
```

---

## chat.py

사용자 질문 API입니다.

```text
POST /api/chat
```

입력 예:

```json
{
  "announcementId": 1,
  "question": "신청 일정은 언제인가?"
}
```

흐름:

```text
chat.py
 ↓
chat_service.py
 ↓
rag.service:answer_question
```

---

## admin_auth.py

관리자 로그인/인증 API입니다.

---

## admin.py

관리자 화면에서 사용하는 공고/문서/오류 관리 API입니다.

---

# 15. backend/app/schemas/

구조:

```text
backend/app/schemas/
├── admin.py
├── admin_auth.py
├── announcement.py
├── chat.py
└── common.py
```

API Request/Response의 Pydantic Schema입니다.

API JSON 형식을 변경하려면 Route만 수정하지 말고 이 영역을 확인해야 합니다.

---

## chat.py

Chat API Contract입니다.

대표 데이터:

```text
announcementId
question
answer
grounded
evidence
```

Frontend와 RAG 사이의 중요한 계약입니다.

---

## announcement.py

공고 목록 및 상세 응답 구조를 정의합니다.

---

# 16. backend/app/services/

구조:

```text
backend/app/services/
├── admin_auth_service.py
├── admin_service.py
├── announcement_service.py
├── chat_service.py
├── pipeline_gateway.py
└── pipeline_persistence.py
```

API Route와 실제 Application Logic 사이의 Service Layer입니다.

---

## announcement_service.py

공고 조회 관련 DB Logic을 담당합니다.

```text
announcements.py
      ↓
announcement_service.py
      ↓
Database
```

---

## chat_service.py

Backend와 RAG 사이의 연결점입니다.

환경변수:

```text
RAG_ANSWER_FUNCTION
```

현재 RAG 진입점:

```text
rag.service:answer_question
```

따라서 Chat API가 RAG를 호출하지 못하는 경우:

```text
backend/app/api/routes/chat.py
backend/app/services/chat_service.py
.env
rag/service.py
```

순서로 확인합니다.

---

## pipeline_gateway.py

Backend에서 Pipeline 기능을 호출하기 위한 Gateway입니다.

Pipeline 실행 기능과 Backend를 연결할 때 이 파일을 확인합니다.

---

## pipeline_persistence.py

Pipeline 결과를 Database에 저장하는 역할을 담당합니다.

```text
Pipeline Output
      ↓
pipeline_persistence.py
      ↓
SQLAlchemy
      ↓
PostgreSQL
```

Offline Pipeline과 Runtime DB 사이의 핵심 연결 지점입니다.

---

## admin_service.py

관리자 기능 관련 Application Logic을 담당합니다.

---

## admin_auth_service.py

관리자 인증 Logic을 담당합니다.

관련 환경변수:

```text
ADMIN_ID
ADMIN_PASSWORD
ADMIN_JWT_SECRET
ADMIN_JWT_EXPIRE_SECONDS
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SAMESITE
ADMIN_COOKIE_SECURE
```

---

# 17. backend/app/db/

구조:

```text
backend/app/db/
├── base.py
└── session.py
```

---

## session.py

SQLAlchemy Database Session을 생성합니다.

DB 연결 문제 발생 시:

```text
.env
backend/app/core/config.py
backend/app/db/session.py
infra/docker-compose.yml
```

를 함께 확인합니다.

---

## base.py

SQLAlchemy Declarative Base 및 Model 연결과 관련된 파일입니다.

---

# 18. backend/app/models/

현재 주요 ORM Model:

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

이 영역은 실제 DB Table 구조와 연결됩니다.

DB 구조를 변경할 때는 반드시:

```text
backend/app/models/
        +
migrations/
```

를 함께 확인합니다.

---

# 19. 주요 DB Model 의미

## announcement.py

서비스에서 보여주는 공고 정보입니다.

---

## document.py

공고와 연결된 원본 문서 정보를 관리합니다.

---

## document_structure.py

문서 Structure 처리 결과와 관련된 데이터를 관리합니다.

---

## chunk.py

RAG 검색 단위인 Chunk입니다.

---

## embedding.py

Chunk에 대응하는 Embedding Vector 정보입니다.

pgvector Retrieval과 직접 연결됩니다.

---

## processing_run.py

특정 문서 Pipeline 실행 단위를 나타냅니다.

---

## processing_artifact.py

Pipeline 실행 중 생성된 Artifact 정보를 관리합니다.

---

## chunk_set.py

특정 처리 결과에서 생성된 Chunk 집합을 관리합니다.

---

## collection_run.py

공고/문서 수집 및 Dataset 처리 단위와 관련된 상태를 관리합니다.

---

## system_state.py

현재 서비스가 사용해야 하는 Active Dataset 등의 상태를 관리합니다.

---

## key_information.py

공고에서 구조화된 주요 정보와 관련된 Model입니다.

---

## error_log.py

관리자에서 확인할 수 있는 오류 기록입니다.

---

# 20. migrations/

구조:

```text
migrations/
├── env.py
├── script.py.mako
└── versions/
```

DB Schema 변경 이력을 관리합니다.

현재 주요 Migration은 다음 영역을 구성합니다.

```text
announcements
collection_runs
documents
processing_runs
processing_artifacts
chunks
embeddings
document_structures
key_information
admin
error_log
active dataset state
```

중요:

ORM Model을 수정했다고 DB가 자동으로 변경되는 것은 아닙니다.

```text
Model 변경
    ↓
Migration 작성
    ↓
Alembic 실행
    ↓
DB Schema 변경
```

순서가 필요합니다.

---

# 21. alembic.ini

경로:

```text
/alembic.ini
```

이 파일은 `backend/app/db/` 안에 넣는 파일이 아닙니다.

Alembic CLI가 Project Root에서 Migration 환경을 찾기 위한 설정 파일이므로 Root에 존재하는 것이 정상입니다.

연결:

```text
alembic.ini
    ↓
migrations/env.py
    ↓
backend/app/models/
    ↓
Database
```

---

# 22. infra/

구조:

```text
infra/
├── docker-compose.yml
└── postgres/
    └── init/
        └── 01-enable-vector.sql
```

---

## docker-compose.yml

개발용 PostgreSQL 환경을 구성합니다.

---

## 01-enable-vector.sql

PostgreSQL의 pgvector Extension을 활성화하기 위한 초기화 SQL입니다.

RAG Vector Search를 위해 필요합니다.

---

# 23. rag/

현재 구조:

```text
rag/
├── __init__.py
├── db_pipeline.py
├── models.py
├── service.py
│
├── generation/
│   ├── __init__.py
│   ├── config.py
│   ├── context_builder.py
│   ├── generator.py
│   ├── llm_client.py
│   ├── models.py
│   └── prompt_builder.py
│
└── retrieval/
    ├── __init__.py
    ├── config.py
    ├── models.py
    └── query_embedding.py
```

현재 Runtime RAG의 중심입니다.

---

# 24. rag/service.py

Backend에서 호출하는 RAG 공식 진입점입니다.

대표 함수:

```text
answer_question()
```

연결:

```text
backend chat_service
       ↓
rag/service.py
       ↓
rag/db_pipeline.py
```

Backend와 RAG를 분리하기 위한 중요한 Boundary입니다.

---

# 25. rag/db_pipeline.py

현재 RAG Runtime의 핵심 파일입니다.

역할:

```text
Question
    ↓
Query Embedding
    ↓
PostgreSQL + pgvector
    ↓
Top-K Chunk Retrieval
    ↓
Generation
```

이 파일은 현재:

```text
선택 공고 제한
Active Dataset 확인
Query Embedding
pgvector 검색
검색 결과 구성
Generation 호출
```

등을 담당합니다.

검색 결과가 이상할 경우 가장 먼저 확인해야 하는 파일 중 하나입니다.

---

# 26. rag/models.py

RAG 계층에서 공통으로 사용하는 Runtime Result 모델을 정의합니다.

Retrieval과 Generation 사이에서 사용하는 결과 구조를 확인할 때 봅니다.

---

# 27. rag/retrieval/

현재 구조:

```text
rag/retrieval/
├── __init__.py
├── config.py
├── models.py
└── query_embedding.py
```

현재 Runtime은 과거 File-based Hybrid Retrieval 구조가 아니라 DB 기반 Retrieval입니다.

---

## query_embedding.py

사용자의 질문을 Vector로 변환합니다.

```text
Question
    ↓
BGE-M3
    ↓
Query Vector
```

Model Loader:

```text
pipeline/embedding/model_loader.py
```

를 재사용합니다.

---

## config.py

Retrieval 관련 설정입니다.

예:

```text
Embedding max length
Top-K 관련 설정
```

실제 Runtime에서 어떤 설정값을 사용하는지는 `rag/db_pipeline.py`와 함께 확인합니다.

---

## models.py

Retrieval Result 관련 데이터 모델입니다.

---

# 28. rag/generation/

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

검색된 Chunk를 최종 자연어 답변으로 변환합니다.

---

## context_builder.py

검색 결과를 LLM에 전달할 Context로 구성합니다.

검색은 정상인데 LLM이 핵심 근거를 제대로 받지 못하는 경우 확인합니다.

---

## prompt_builder.py

LLM Prompt를 생성합니다.

답변 스타일, 근거 사용 방식, 답변 제한 조건 등에 영향을 줍니다.

---

## llm_client.py

실제 LLM Runtime을 호출하는 Client 계층입니다.

LLM 서버 연결 실패, Timeout, Response parsing 등의 문제가 발생하면 확인합니다.

---

## generator.py

Generation 전체 흐름을 조정합니다.

```text
Retrieved Results
       ↓
Context Builder
       ↓
Prompt Builder
       ↓
LLM Client
       ↓
Generated Answer
```

현재 다음과 같은 응답이 발생한다면:

```text
grounded=true
evidence 존재
answer=fallback
```

이 영역을 우선 확인해야 합니다.

---

## models.py

Generation 결과와 Source 관련 데이터 구조입니다.

---

## config.py

Generation 관련 설정입니다.

---

# 29. frontend/user/

구조:

```text
frontend/user/
├── index.html
├── package.json
├── package-lock.json
├── postcss.config.js
├── tailwind.config.js
├── tsconfig.json
├── vite.config.ts
├── public/
└── src/
```

React + TypeScript + Vite 기반 사용자 Frontend입니다.

---

# 30. frontend/user/src/config.ts

Frontend API Base의 단일 기준입니다.

현재:

```typescript
export const API_BASE_URL = "/api";
```

다른 Component에서 API 주소를 새로 하드코딩하지 않습니다.

---

# 31. ListScreen.tsx

경로:

```text
frontend/user/src/components/screens/ListScreen.tsx
```

역할:

```text
GET /api/announcements
```

공고 목록 조회 및 화면 표시를 담당합니다.

---

# 32. DetailScreen.tsx

경로:

```text
frontend/user/src/components/screens/DetailScreen.tsx
```

역할:

```text
공고 상세 조회
Chat 질문
Evidence 표시
```

API:

```text
GET /api/announcements/{id}

POST /api/chat
```

Chat 화면 문제가 발생하면 이 파일과 Backend `chat.py`를 함께 확인합니다.

---

# 33. frontend/user/vite.config.ts

Vite 개발 서버 설정입니다.

특히:

```text
/api
```

요청을 FastAPI로 전달하는 Proxy 설정을 확인합니다.

Frontend 화면은 뜨는데 API 호출이 실패하는 경우 중요한 진단 지점입니다.

---

# 34. frontend/admin/

관리자 Frontend입니다.

구조:

```text
frontend/admin/
├── announcement.html
├── document.html
├── error.html
├── login.html
├── components/
├── css/
├── js/
└── serve_admin.py
```

React가 아니라 정적 HTML/CSS/JavaScript 기반입니다.

---

# 35. frontend/admin/serve_admin.py

Admin Frontend Static Server 및 API Proxy입니다.

구조:

```text
Browser
   ↓
serve_admin.py
   ├── HTML/CSS/JS
   │
   └── /api/*
          ↓
       FastAPI
```

현재 FastAPI 기본 연결 포트는 프로젝트 실행 환경 기준 `8000`을 사용합니다.

---

# 36. tests/

현재 테스트 영역은 자동화 Test Code보다는 Pipeline 검증용 Fixture 문서가 중심입니다.

구조:

```text
tests/
└── fixtures/
    └── documents/
        ├── announcement_001/
        ├── announcement_002/
        ├── announcement_003/
        └── announcement_004/
```

여기에 HWP/HWPX 테스트 문서가 존재합니다.

`run_pipeline.py`가 Pipeline 검증 과정에서 이 문서들을 사용합니다.

---

# 37. crawler/

현재 구조:

```text
crawler/
└── __init__.py
```

현재 실제 Crawler 구현은 존재하지 않습니다.

따라서 현재 프로젝트 설명에서:

```text
Crawler가 LH에서 자동으로 공고를 수집한다.
```

라고 단정하면 안 됩니다.

현재는 향후 Crawler 구현을 위한 Module 영역으로 봅니다.

---

# 38. outputs/

Pipeline 실행 결과가 생성되는 Runtime Artifact 영역입니다.

예:

```text
Parser 결과
Normalizer 결과
Structure 결과
Chunk 결과
Embedding 결과
```

이 디렉터리는 Source Code가 아닙니다.

파일 크기가 커질 수 있으며 Pipeline 실행 시 재생성될 수 있습니다.

---

# 39. requirements.txt

Python Project 전체 의존성입니다.

대표 영역:

```text
FastAPI
SQLAlchemy
PostgreSQL
Alembic
pgvector
JPype
FlagEmbedding
Transformers
PyTorch
CUDA
```

Embedding 환경은 GPU/CUDA 버전의 영향을 받을 수 있으므로 의존성 변경 시 주의합니다.

---

# 40. .env

실제 Runtime 환경변수입니다.

대표적으로 다음 영역의 설정이 포함될 수 있습니다.

```text
Database
Admin Authentication
RAG Function
Pipeline Gateway
LLM
```

실제 Secret 값은 문서에 기록하지 않습니다.

---

# 41. .env.example

프로젝트 실행에 필요한 환경변수의 Template 역할을 해야 합니다.

`.env`에 새로운 필수 설정을 추가하면 `.env.example`에도 변수 이름과 안전한 예시를 반영합니다.

Secret 값은 넣지 않습니다.

---

# 42. 기능별 수정 위치 Quick Reference

| 수정하려는 기능 | 먼저 확인할 위치 |
|---|---|
| HWP Parsing | `pipeline/parser/hwp_parser.py` |
| HWPX Parsing | `pipeline/parser/hwpx_parser.py` |
| Text 정규화 | `pipeline/normalizer/document_normalizer.py` |
| 문서 구조화 | `pipeline/structure/` |
| Table 구조화 | `pipeline/structure/build_table_step3.py` |
| Chunk 분할 | `pipeline/chunking/` |
| Embedding 생성 | `pipeline/embedding/` |
| Embedding Model | `pipeline/embedding/model_loader.py` |
| 전체 Pipeline | `run_pipeline.py` |
| Pipeline → DB | `backend/app/services/pipeline_persistence.py` |
| 질문 Embedding | `rag/retrieval/query_embedding.py` |
| Vector 검색 | `rag/db_pipeline.py` |
| LLM Context | `rag/generation/context_builder.py` |
| Prompt | `rag/generation/prompt_builder.py` |
| LLM 호출 | `rag/generation/llm_client.py` |
| 답변 생성 | `rag/generation/generator.py` |
| RAG 진입점 | `rag/service.py` |
| Chat API | `backend/app/api/routes/chat.py` |
| RAG 연결 | `backend/app/services/chat_service.py` |
| 공고 API | `backend/app/api/routes/announcements.py` |
| DB Session | `backend/app/db/session.py` |
| DB Table | `backend/app/models/` |
| DB Migration | `migrations/` |
| 사용자 목록 | `ListScreen.tsx` |
| 사용자 상세/Chat | `DetailScreen.tsx` |
| Front API Base | `frontend/user/src/config.ts` |
| Vite Proxy | `frontend/user/vite.config.ts` |
| Admin Front | `frontend/admin/` |

---

# 43. 문제 발생 시 수정 위치 판단

## Frontend에서 공고 목록이 안 나오는 경우

확인 순서:

```text
frontend/user/src/config.ts
    ↓
frontend/user/vite.config.ts
    ↓
ListScreen.tsx
    ↓
GET /api/announcements
    ↓
announcements.py
    ↓
announcement_service.py
    ↓
Database
```

---

## Chat 요청 자체가 실패하는 경우

```text
DetailScreen.tsx
    ↓
POST /api/chat
    ↓
chat.py
    ↓
chat_service.py
    ↓
RAG_ANSWER_FUNCTION
    ↓
rag/service.py
```

---

## Evidence가 검색되지 않는 경우

```text
rag/service.py
    ↓
rag/db_pipeline.py
    ↓
query_embedding.py
    ↓
PostgreSQL / pgvector
    ↓
chunks / embeddings
```

이 경우 Generation부터 수정하지 않습니다.

---

## Evidence는 정상인데 답변만 실패하는 경우

예:

```json
{
  "grounded": true,
  "evidence": [
    {
      "content": "관련 공고문 내용..."
    }
  ],
  "answer": "현재 답변 생성 품질이 안정적이지 않아..."
}
```

우선 확인:

```text
rag/generation/context_builder.py
rag/generation/prompt_builder.py
rag/generation/llm_client.py
rag/generation/generator.py
```

이 경우 Frontend/Parser/DB를 무작정 수정하지 않습니다.

---

## Pipeline 결과가 잘못된 경우

오류가 처음 발생한 Stage를 찾습니다.

```text
원본 문서
 ↓
Parsed
 ↓
Normalized
 ↓
Structured
 ↓
Chunks
 ↓
Embeddings
```

예를 들어 Parsed 결과부터 틀렸다면 Chunking을 수정하지 않습니다.

Parser를 먼저 수정합니다.

반대로 Structured 결과까지 정상인데 Chunk가 잘못됐다면 Parser/Normalizer를 건드리지 않고 Chunking을 확인합니다.

---

# 44. 삭제 전 반드시 확인해야 하는 것

파일이 사용되지 않는 것처럼 보여도 바로 삭제하지 않습니다.

먼저 전체 참조를 검색합니다.

예:

```bash
grep -RHn "파일명또는함수명" \
  backend pipeline rag config run_pipeline.py \
  --include='*.py' \
  --exclude-dir='__pycache__'
```

확인 대상:

```text
import
function call
subprocess
dynamic import
환경변수 기반 import
run_pipeline.py의 Path reference
```

특히 다음은 단순 grep만으로 놓칠 수 있습니다.

```text
RAG_ANSWER_FUNCTION
Pipeline Gateway Function
subprocess 실행 파일
```

---

# 45. 프로젝트 구조 변경 원칙

프로젝트를 정리하거나 리팩터링할 때 다음 순서를 지킵니다.

```text
1. 현재 호출 관계 확인
2. 실제 Runtime 사용 여부 확인
3. 중복 구현 확인
4. 하나의 Source of Truth 결정
5. 호출 코드 변경
6. Legacy 코드 삭제
7. 전체 Reference 검색
8. Python Import 검증
9. Frontend Build
10. API Smoke Test
```

---

# 46. Source of Truth 원칙

같은 설정이나 기능을 여러 파일에서 중복 정의하지 않습니다.

예:

Frontend API Base:

```text
frontend/user/src/config.ts
```

Pipeline Path:

```text
config/paths.py
```

Chat API Contract:

```text
backend/app/schemas/chat.py
```

RAG Backend Entry:

```text
rag/service.py
```

DB Schema:

```text
backend/app/models/
+
migrations/
```

Embedding Model Loading:

```text
pipeline/embedding/model_loader.py
```

---

# 47. 프로젝트를 AI에게 전달할 때

AI에게 프로젝트를 분석시키는 경우 다음 정보를 먼저 제공합니다.

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
```

그 후 수정하려는 기능의 Source Code를 제공합니다.

예:

```text
"Chat 답변 생성 문제를 수정해줘."
```

라면 최소 확인 대상:

```text
rag/service.py
rag/db_pipeline.py
rag/generation/
backend/app/services/chat_service.py
backend/app/api/routes/chat.py
```

Evidence가 이미 정상적으로 검색된 것이 확인되었다면 Generation 영역을 우선 분석합니다.

---

# 48. 핵심 요약

DDOKBOT의 핵심 구조는 다음과 같습니다.

```text
                ┌──────────────────┐
                │ HWP / HWPX       │
                └────────┬─────────┘
                         ↓
                ┌──────────────────┐
                │    Pipeline      │
                │                  │
                │ Parser           │
                │ Normalizer       │
                │ Structure        │
                │ Chunking         │
                │ Embedding        │
                └────────┬─────────┘
                         ↓
                ┌──────────────────┐
                │   PostgreSQL     │
                │   + pgvector     │
                └────────┬─────────┘
                         ↑
                         │
                ┌────────┴─────────┐
                │       RAG        │
                │                  │
Question ──────▶│ Query Embedding  │
                │ DB Retrieval     │
                │ Generation       │
                └────────┬─────────┘
                         ↓
                ┌──────────────────┐
                │     FastAPI      │
                └────────┬─────────┘
                         ↓
                ┌──────────────────┐
                │    Frontend      │
                └──────────────────┘
```

프로젝트를 수정할 때 가장 중요한 원칙은:

> **문제가 발생한 Stage를 먼저 찾고, 그 Stage의 책임 범위 안에서 수정한다.**

하나의 문제 때문에 Parser부터 Frontend까지 전체 코드를 동시에 수정하지 않습니다.
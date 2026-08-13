# DDOKBOT RAG System

> 이 문서는 DDOKBOT의 Runtime RAG 질의응답 구조를 설명합니다.
>
> 새로운 개발자 또는 AI가 이 문서만 읽고도 다음 내용을 이해할 수 있도록 작성되었습니다.
>
> - 사용자 질문이 어느 API로 들어오는지
> - Backend에서 RAG를 어떻게 호출하는지
> - 질문 Embedding이 어디서 생성되는지
> - PostgreSQL + pgvector에서 어떤 방식으로 Chunk를 찾는지
> - 검색 결과가 Generation Context로 어떻게 전달되는지
> - LLM이 어디에서 호출되는지
> - 최종 Answer와 Evidence가 어떻게 API 응답으로 변환되는지
> - 문제가 발생했을 때 어느 계층부터 확인해야 하는지

---

# 1. RAG의 역할

DDOKBOT의 RAG는 사용자가 선택한 공고문을 기준으로 질문에 답변합니다.

예:

```text
사용자 질문
"신청 일정은 언제인가?"
```

전체 흐름:

```text
Frontend
   ↓
POST /api/chat
   ↓
FastAPI
   ↓
Chat Service
   ↓
RAG Service
   ↓
DB RAG Pipeline
   ↓
Query Embedding
   ↓
PostgreSQL + pgvector
   ↓
Relevant Chunks
   ↓
Generation Context
   ↓
Prompt
   ↓
LLM
   ↓
Answer + Evidence
   ↓
Frontend
```

---

# 2. Pipeline RAG와 Runtime RAG의 차이

DDOKBOT에는 크게 두 가지 흐름이 있습니다.

## Document Ingestion Pipeline

문서를 사전에 처리합니다.

```text
HWP/HWPX
→ Parse
→ Normalize
→ Structure
→ Chunk
→ Embedding
→ PostgreSQL
```

관련 문서:

```text
docs/PIPELINE.md
```

---

## Runtime RAG

사용자의 질문에 실시간으로 답합니다.

```text
Question
→ Query Embedding
→ DB Retrieval
→ Context
→ LLM
→ Answer
```

즉 질문할 때마다 HWP 파일을 다시 Parsing하거나 Chunking하지 않습니다.

이미 DB에 저장된 Chunk와 Embedding을 사용합니다.

---

# 3. Runtime RAG Entry Point

Frontend에서 질문을 보내는 API:

```text
POST /api/chat
```

Request 예:

```json
{
  "announcementId": 1,
  "question": "신청 일정은 언제인가?"
}
```

Response 개념:

```json
{
  "answer": "...",
  "grounded": true,
  "evidence": [
    {
      "chunkId": "...",
      "sectionTitle": "...",
      "content": "...",
      "score": 0.58
    }
  ]
}
```

---

# 4. Frontend Chat Request

사용자 Frontend:

```text
frontend/user/src/components/screens/DetailScreen.tsx
```

API Base:

```text
frontend/user/src/config.ts
```

현재:

```ts
export const API_BASE_URL = "/api";
```

질문 전송:

```text
DetailScreen.tsx
      ↓
POST /api/chat
```

전송 데이터:

```text
announcementId
question
```

중요:

`announcementId`는 사용자가 현재 보고 있는 공고의 ID입니다.

따라서 RAG는 전체 공고를 대상으로 답하는 것이 아니라
선택된 공고를 검색 범위로 사용합니다.

---

# 5. FastAPI Chat Route

파일:

```text
backend/app/api/routes/chat.py
```

역할:

```text
HTTP Request
    ↓
Request Schema Validation
    ↓
Chat Service 호출
    ↓
Response Schema 반환
```

개념적인 호출:

```text
POST /api/chat
       ↓
chat.py
       ↓
answer_question_via_rag()
```

---

# 6. Chat Request Schema

파일:

```text
backend/app/schemas/chat.py
```

주요 입력:

```text
announcementId
question
```

Python 내부에서는:

```text
announcement_id
question
```

형태로 처리됩니다.

현재 `announcementId`는 Pydantic alias로 연결되어 있습니다.

즉 Frontend는:

```json
{
  "announcementId": 1
}
```

을 보내고 Backend 내부에서는:

```python
announcement_id
```

로 사용할 수 있습니다.

---

# 7. Chat Service

파일:

```text
backend/app/services/chat_service.py
```

역할:

```text
API Layer
   ↓
RAG Function Adapter
   ↓
rag.service.answer_question()
```

현재 환경변수:

```text
RAG_ANSWER_FUNCTION
```

을 통해 RAG 함수 경로를 지정할 수 있습니다.

현재 사용해야 하는 함수:

```text
rag.service:answer_question
```

개념:

```text
RAG_ANSWER_FUNCTION=rag.service:answer_question
```

---

# 8. Chat Service의 목적

Backend API가 RAG 구현 세부사항에 직접 의존하지 않도록 중간 Adapter 역할을 합니다.

즉:

```text
API
 ↓
chat_service.py
 ↓
RAG
```

구조입니다.

따라서 RAG 내부 구현이 변경되어도 API Route 자체를 크게 변경하지 않는 것이 좋습니다.

---

# 9. RAG Service

파일:

```text
rag/service.py
```

Runtime RAG의 외부 진입점입니다.

핵심 함수:

```python
answer_question(
    announcement_id,
    question,
)
```

호출 구조:

```text
chat_service.py
      ↓
rag.service.answer_question()
      ↓
DBRAGPipeline
```

---

# 10. RAG Service의 책임

`rag/service.py`는 다음 역할을 담당합니다.

```text
입력 검증
↓
announcement_id 검증
↓
질문 문자열 정리
↓
DB RAG Pipeline 호출
↓
Generation 결과 수신
↓
API용 Evidence 생성
↓
Answer 결과 반환
```

RAG 전체 구현을 `service.py`에 몰아넣지 않습니다.

실제 검색과 Generation orchestration은:

```text
rag/db_pipeline.py
```

가 담당합니다.

---

# 11. DB RAG Pipeline

파일:

```text
rag/db_pipeline.py
```

현재 Runtime RAG의 핵심 파일입니다.

개념:

```text
Question
   ↓
BGE-M3 Query Embedding
   ↓
PostgreSQL + pgvector
   ↓
Selected Announcement Top-K
   ↓
RetrievalResult
   ↓
Generation
```

---

# 12. 현재 Retrieval 방식

현재 Runtime RAG는 기존 File 기반 Hybrid Search가 아니라
DB 기반 pgvector 검색을 사용합니다.

즉 현재 핵심 검색 구조는:

```text
Query
 ↓
Dense Embedding
 ↓
PostgreSQL pgvector
 ↓
Vector Similarity
 ↓
Top-K
```

입니다.

이전 구조에서 존재했던:

```text
BM25
Hybrid Search
RRF
File Corpus Loader
Reranker
```

는 현재 Runtime DB RAG의 실행 경로가 아닙니다.

삭제된 Legacy 구현을 다시 기준으로 삼지 않습니다.

---

# 13. Query Embedding

파일:

```text
rag/retrieval/query_embedding.py
```

주요 함수:

```python
embed_query()
```

역할:

```text
사용자 Question
      ↓
BGE-M3
      ↓
Dense Vector
      ↓
L2 Normalize
```

---

# 14. Embedding Model Loader

Query Embedding은 Document Embedding과 동일한 Model Loader를 사용합니다.

파일:

```text
pipeline/embedding/model_loader.py
```

관계:

```text
Document Embedding
pipeline/embedding/
        │
        │ same model
        ▼
BAAI/bge-m3
        ▲
        │ same model
        │
Query Embedding
rag/retrieval/query_embedding.py
```

현재 모델:

```text
BAAI/bge-m3
```

현재 확인된 Vector Dimension:

```text
1024
```

---

# 15. Document Vector와 Query Vector

RAG 검색이 정상적으로 동작하려면:

```text
Document Vector
```

와

```text
Query Vector
```

가 같은 Embedding Model에서 생성되어야 합니다.

현재:

```text
Document → BAAI/bge-m3
Question → BAAI/bge-m3
```

구조입니다.

Embedding Model을 변경하면 두 경로를 반드시 함께 확인해야 합니다.

---

# 16. Retrieval Configuration

파일:

```text
rag/retrieval/config.py
```

Retrieval 관련 설정을 관리합니다.

DB RAG Pipeline은 이 설정을 사용하여 검색 동작을 결정할 수 있습니다.

추가로 Runtime에서:

```text
RAG_DB_TOP_K
```

환경변수를 사용할 수 있습니다.

현재 코드의 정확한 기본값은:

```text
rag/db_pipeline.py
```

를 Source of Truth로 사용합니다.

---

# 17. PostgreSQL Retrieval

DB 연결:

```text
backend/app/db/session.py
```

Runtime 검색:

```text
rag/db_pipeline.py
```

개념:

```text
Query Vector
     ↓
SQLAlchemy
     ↓
PostgreSQL
     ↓
pgvector
     ↓
Similarity Search
```

---

# 18. 검색 범위

RAG 검색에서 매우 중요한 조건:

```text
announcement_id
```

입니다.

사용자가 공고 1을 보고 있다면:

```text
announcement_id = 1
```

인 문서/Chunk 범위에서 검색해야 합니다.

다른 공고의 Chunk가 검색 결과에 섞이면 안 됩니다.

---

# 19. Active Dataset

DB에 존재하는 모든 Chunk를 검색 대상으로 사용하지 않습니다.

Pipeline Persistence 구조에는:

```text
ProcessingRun
ChunkSet
```

의 Active 상태가 존재합니다.

개념:

```text
Announcement
    ↓
Document
    ↓
Active ProcessingRun
    ↓
Active ChunkSet
    ↓
Chunks
    ↓
Embeddings
```

Runtime RAG는 현재 활성화된 데이터셋을 기준으로 검색해야 합니다.

---

# 20. DB Retrieval 결과

DB 검색 결과는 Generation 계층에서 사용할 수 있도록 내부 Retrieval Result 형태로 변환됩니다.

현재 공통 모델:

```text
rag/models.py
```

Retrieval 관련 모델:

```text
rag/retrieval/models.py
```

---

# 21. RetrievalResult

현재 Runtime에서는 검색 결과를 `RetrievalResult` 형태로 Generation에 전달하도록 구조를 단순화했습니다.

개념적인 데이터:

```text
chunk
score
rank
content
section information
source information
```

즉 Generation 계층은 DB SQL 결과를 직접 알 필요가 없습니다.

```text
PostgreSQL Row
      ↓
DB RAG Pipeline
      ↓
RetrievalResult
      ↓
Generation
```

구조를 유지합니다.

---

# 22. 현재 Reranker 상태

현재 Runtime DB RAG에는 별도의 Cross Encoder Reranker가 실행되지 않습니다.

즉:

```text
BGE Query Embedding
→ pgvector Top-K
→ Generation
```

입니다.

과거 `rag/reranker/` 구현은 현재 Runtime 구조에서 제거되었습니다.

따라서 다음 용어가 남아 있다면 Legacy 흔적 여부를 확인해야 합니다.

```text
RerankResult
rerank_results
load_reranker_model
rag.reranker
```

새 코드에서는 가능하면 현재 의미에 맞는:

```text
RetrievalResult
retrieval_results
```

형태를 사용합니다.

---

# 23. Generation Layer

Generation 관련 코드:

```text
rag/generation/
```

현재 구조:

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

---

# 24. Generation 전체 흐름

```text
Retrieval Results
       ↓
context_builder.py
       ↓
Context
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
GeneratedAnswer
```

---

# 25. Context Builder

파일:

```text
rag/generation/context_builder.py
```

역할:

```text
검색된 Chunk
    ↓
상위 결과 선택
    ↓
LLM이 읽을 Context 생성
```

Retrieval 결과 전체를 무조건 LLM에 넣는 것이 아니라
Generation 설정에 따라 필요한 범위만 Context로 사용합니다.

---

# 26. Context가 중요한 이유

Retrieval이 정확해도 Context 구성이 잘못되면 LLM 답변 품질이 떨어질 수 있습니다.

예:

```text
검색 결과에는 일정 Chunk가 있음
```

그런데:

```text
Context Builder가 해당 Chunk를 제외함
```

이면 LLM은 일정 정보를 볼 수 없습니다.

따라서 RAG 문제를 분석할 때:

```text
Retrieval 결과
```

와

```text
실제 LLM Context
```

를 구분해서 확인해야 합니다.

---

# 27. Prompt Builder

파일:

```text
rag/generation/prompt_builder.py
```

역할:

```text
System Instruction
+
User Question
+
Retrieved Context
=
LLM Prompt
```

Prompt는 LLM에게 다음과 같은 행동을 요구해야 합니다.

```text
공고문 근거 기반 답변
근거 없는 내용 생성 금지
질문에 직접 답변
문서에 없는 정보 추측 금지
```

Prompt 품질은 최종 Answer 품질에 직접 영향을 줍니다.

---

# 28. LLM Client

파일:

```text
rag/generation/llm_client.py
```

역할:

```text
Prompt
 ↓
LLM Server
 ↓
Raw LLM Response
```

현재 프로젝트에서는 `llama.cpp` 기반 LLM Server를 별도로 실행하는 구조입니다.

즉 FastAPI 자체가 LLM Model을 직접 Serving하는 것이 아닙니다.

개념:

```text
FastAPI
   ↓
RAG Generation
   ↓
HTTP
   ↓
llama.cpp Server
   ↓
Qwen Model
```

---

# 29. Generation Config

파일:

```text
rag/generation/config.py
```

Generation 관련 설정의 Source of Truth입니다.

예:

```text
Context Top-K
LLM Endpoint
Generation Parameter
Timeout
```

정확한 현재 값은 해당 파일을 확인합니다.

---

# 30. Generator

파일:

```text
rag/generation/generator.py
```

Generation 전체를 조합합니다.

개념:

```text
generate_answer()
      ↓
build context
      ↓
build prompt
      ↓
call LLM
      ↓
validate response
      ↓
GeneratedAnswer
```

---

# 31. GeneratedAnswer

파일:

```text
rag/generation/models.py
```

LLM 결과를 Runtime에서 사용할 수 있는 형태로 표현합니다.

최종적으로:

```text
Answer
Grounding 상태
Evidence Source
```

등을 API 계층에서 사용할 수 있도록 전달합니다.

---

# 32. Evidence 생성

사용자에게 단순 Answer만 반환하지 않고 검색 근거도 함께 반환합니다.

예:

```json
{
  "chunkId": "...",
  "sectionTitle": "선착순 동호지정 및 계약 안내",
  "content": "일정: '26.07.23.(목) 오전 10시 ~ 별도 공지시까지",
  "score": 0.58
}
```

Evidence는 사용자가:

```text
"AI가 왜 이렇게 답했는가?"
```

를 확인할 수 있도록 하기 위한 것입니다.

---

# 33. Grounded

Response에는:

```text
grounded
```

값이 존재합니다.

예:

```json
{
  "grounded": true
}
```

이는 검색된 공고문 근거가 존재하는지 판단하는 데 사용됩니다.

중요:

```text
grounded = true
```

라고 해서 반드시 LLM Answer 생성이 성공했다는 의미는 아닙니다.

Retrieval은 성공했지만 Generation이 실패할 수도 있습니다.

---

# 34. 현재 확인된 실제 사례

질문:

```text
신청 일정은 언제인가?
```

Retrieval 결과에는 다음과 같은 정확한 근거가 검색되었습니다.

```text
일 정:
‘26.07.23.(목) 오전 10시 ~ 별도 공지시까지

운영시간:
10:00~16:00
12:00~13:00 및 주말·공휴일 미운영
```

즉 해당 요청에서:

```text
Retrieval = 성공
```

했습니다.

하지만 Answer:

```text
공고문 근거는 확인되었지만 현재 답변 생성 품질이
안정적이지 않아 정확한 문장으로 제공하지 못했습니다.
잠시 후 다시 시도해 주세요.
```

가 반환되었습니다.

이 경우 문제를:

```text
pgvector 검색 실패
```

로 판단하면 안 됩니다.

검색 Evidence가 정상적으로 존재하기 때문입니다.

우선 확인 대상은:

```text
rag/generation/
LLM Server
Generation Validation
```

입니다.

---

# 35. RAG 문제를 3단계로 분리하기

RAG 문제는 반드시 다음 세 영역으로 분리합니다.

```text
Retrieval
Generation
API/UI
```

---

## A. Retrieval 문제

증상:

```text
Evidence가 없음
관련 없는 Chunk 검색
다른 공고 Chunk 검색
Score가 이상함
```

확인:

```text
rag/db_pipeline.py
rag/retrieval/query_embedding.py
rag/retrieval/config.py
DB Chunk/Embedding
Active ProcessingRun
Active ChunkSet
```

---

## B. Generation 문제

증상:

```text
Evidence는 정확함
하지만 Answer가 실패함
Fallback Answer 반환
LLM 응답 Parsing 실패
Timeout
```

확인:

```text
rag/generation/generator.py
rag/generation/context_builder.py
rag/generation/prompt_builder.py
rag/generation/llm_client.py
rag/generation/config.py
```

---

## C. API/UI 문제

증상:

```text
curl은 정상
Browser만 실패
Frontend fetch 실패
404
CORS
Proxy 문제
```

확인:

```text
backend/app/api/
frontend/user/src/config.ts
frontend/user/vite.config.ts
frontend/admin/serve_admin.py
```

---

# 36. RAG API 직접 테스트

Frontend를 거치지 않고 Backend를 직접 테스트합니다.

```bash
curl -i \
  -X POST \
  http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "announcementId": 1,
    "question": "신청 일정은 언제인가?"
  }'
```

정상 HTTP:

```text
HTTP/1.1 200 OK
```

그 다음 JSON에서 확인:

```text
answer
grounded
evidence
```

---

# 37. Retrieval 성공 여부 판단

다음과 같이 Evidence가 있다면:

```json
{
  "grounded": true,
  "evidence": [
    {
      "content": "...신청 일정..."
    }
  ]
}
```

최소한:

```text
Frontend → API
API → RAG
Query Embedding
DB Connection
pgvector Retrieval
Evidence Conversion
```

까지는 상당 부분 정상이라고 볼 수 있습니다.

---

# 38. Generation Server 확인

Retrieval은 정상인데 Answer가 Fallback이면
LLM Server 상태를 확인합니다.

먼저 Generation Config 확인:

```bash
cd /home/ubuntu/ddokbot/one-cycle

cat rag/generation/config.py
```

LLM Client 확인:

```bash
sed -n '1,260p' rag/generation/llm_client.py
```

Generator 확인:

```bash
sed -n '1,260p' rag/generation/generator.py
```

이 세 파일을 함께 봐야 실제 LLM Endpoint와 실패 조건을 확인할 수 있습니다.

---

# 39. Backend와 RAG 연결 확인

```bash
grep -RHnE \
'RAG_ANSWER_FUNCTION|answer_question_via_rag|answer_question|DBRAGPipeline' \
backend rag \
--include='*.py'
```

정상 구조는 개념적으로:

```text
chat.py
 ↓
chat_service.py
 ↓
rag/service.py
 ↓
rag/db_pipeline.py
```

가 보여야 합니다.

---

# 40. Query Embedding 연결 확인

```bash
grep -RHnE \
'embed_query|query_embedding|load_bge_m3_model' \
rag pipeline \
--include='*.py'
```

현재 핵심:

```text
rag/db_pipeline.py
    ↓
rag/retrieval/query_embedding.py
    ↓
pipeline/embedding/model_loader.py
```

입니다.

---

# 41. RAG에서 DB까지 연결

```text
rag/db_pipeline.py
        │
        ▼
backend/app/db/session.py
        │
        ▼
SQLAlchemy
        │
        ▼
PostgreSQL
        │
        ▼
pgvector
```

DB 연결 문제는 RAG 내부에서 별도의 DB 연결 코드를 새로 만들기보다
Backend의 공통 Session 설정을 사용합니다.

---

# 42. Runtime RAG 전체 코드 연결

```text
frontend/user/
DetailScreen.tsx
       │
       │ POST /api/chat
       ▼
backend/app/api/routes/chat.py
       │
       ▼
backend/app/services/chat_service.py
       │
       ▼
rag/service.py
       │
       ▼
rag/db_pipeline.py
       │
       ├───────────────┐
       │               │
       ▼               ▼
query_embedding.py   PostgreSQL
       │               │
       ▼               ▼
BGE-M3             pgvector
       │               │
       └───────┬───────┘
               ▼
        RetrievalResult
               │
               ▼
rag/generation/context_builder.py
               │
               ▼
rag/generation/prompt_builder.py
               │
               ▼
rag/generation/llm_client.py
               │
               ▼
          llama.cpp
               │
               ▼
rag/generation/generator.py
               │
               ▼
        GeneratedAnswer
               │
               ▼
         rag/service.py
               │
               ▼
         ChatResponse
               │
               ▼
          Frontend UI
```

---

# 43. 수정 시 영향 범위

## Query Embedding 수정

확인:

```text
rag/retrieval/query_embedding.py
pipeline/embedding/model_loader.py
pipeline/embedding/
DB Embedding Dimension
```

---

## Retrieval SQL 수정

확인:

```text
rag/db_pipeline.py
backend/app/models/
migrations/
```

---

## Retrieval Result 구조 수정

확인:

```text
rag/models.py
rag/db_pipeline.py
rag/generation/context_builder.py
rag/generation/generator.py
rag/service.py
```

---

## Prompt 수정

확인:

```text
rag/generation/prompt_builder.py
rag/generation/generator.py
```

DB/Pipeline까지 수정할 필요는 없습니다.

---

## LLM Endpoint 수정

확인:

```text
rag/generation/config.py
rag/generation/llm_client.py
.env
```

---

## API Response 수정

확인:

```text
backend/app/schemas/chat.py
backend/app/api/routes/chat.py
backend/app/services/chat_service.py
rag/service.py
frontend/user/src/components/screens/DetailScreen.tsx
```

---

# 44. AI가 RAG 문제를 수정할 때 전달할 파일

최소:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/PIPELINE.md
docs/RAG.md

backend/app/api/routes/chat.py
backend/app/schemas/chat.py
backend/app/services/chat_service.py

rag/service.py
rag/db_pipeline.py
rag/models.py
rag/retrieval/
rag/generation/
```

DB 검색 문제라면 추가:

```text
backend/app/db/
backend/app/models/
migrations/
```

Frontend 문제라면 추가:

```text
frontend/user/src/config.ts
frontend/user/vite.config.ts
frontend/user/src/components/screens/DetailScreen.tsx
```

---

# 45. AI가 먼저 판단해야 할 것

RAG 문제를 받으면 무작정 코드를 수정하지 말고 먼저 다음을 판단합니다.

```text
1. HTTP 요청 자체가 성공하는가?
2. announcementId가 정확한가?
3. Evidence가 반환되는가?
4. Evidence가 질문과 관련 있는가?
5. Retrieval Score가 존재하는가?
6. grounded가 true인가?
7. LLM 호출이 성공하는가?
8. LLM Raw Response가 정상인가?
9. Generator가 Response를 거부하는가?
10. Frontend가 정상 Response를 표시하는가?
```

이 순서를 지키면 문제 범위를 빠르게 줄일 수 있습니다.

---

# 46. 현재 프로젝트에서 특히 주의할 점

현재 프로젝트는 구조 정리 과정에서 기존 File 기반 RAG 코드를 제거했습니다.

따라서 인터넷 예제나 과거 README를 보고 다음 구조를 다시 추가하지 않습니다.

```text
BM25
HybridSearcher
Corpus Loader
RRF Fusion
Cross Encoder Reranker
File Vector Search
```

현재 Runtime Source of Truth:

```text
rag/db_pipeline.py
```

입니다.

---

# 47. RAG Source of Truth

| 영역 | Source of Truth |
|---|---|
| HTTP Chat API | `backend/app/api/routes/chat.py` |
| Chat Schema | `backend/app/schemas/chat.py` |
| API ↔ RAG Adapter | `backend/app/services/chat_service.py` |
| RAG Entry | `rag/service.py` |
| Runtime RAG | `rag/db_pipeline.py` |
| Common RAG Model | `rag/models.py` |
| Query Embedding | `rag/retrieval/query_embedding.py` |
| Retrieval Config | `rag/retrieval/config.py` |
| Generation Config | `rag/generation/config.py` |
| Context | `rag/generation/context_builder.py` |
| Prompt | `rag/generation/prompt_builder.py` |
| LLM Client | `rag/generation/llm_client.py` |
| Generator | `rag/generation/generator.py` |
| Generation Model | `rag/generation/models.py` |
| DB Connection | `backend/app/db/session.py` |

---

# 48. 핵심 요약

현재 DDOKBOT Runtime RAG는 다음 구조입니다.

```text
POST /api/chat
      ↓
chat_service
      ↓
rag.service
      ↓
DBRAGPipeline
      ↓
BGE-M3 Query Embedding
      ↓
PostgreSQL + pgvector
      ↓
Selected Announcement Top-K Chunks
      ↓
Context Builder
      ↓
Prompt Builder
      ↓
llama.cpp / Qwen
      ↓
Generated Answer
      ↓
Answer + Grounded + Evidence
```

문제가 발생하면 가장 먼저:

```text
Evidence가 정상인가?
```

를 확인합니다.

Evidence가 잘못되었다면:

```text
Retrieval 문제
```

Evidence는 정확하지만 Answer만 실패한다면:

```text
Generation 문제
```

`curl`에서는 정상인데 Browser에서만 실패한다면:

```text
Frontend / Proxy 문제
```

로 범위를 나누어 디버깅합니다.

현재 확인된 `"신청 일정은 언제인가?"` 사례는 관련 일정 Evidence가 정상적으로 검색되었으므로,
우선적으로 Retrieval보다 **Generation 계층을 조사해야 하는 상태**입니다.
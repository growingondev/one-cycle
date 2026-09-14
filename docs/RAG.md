# RAG

> 기준 브랜치: `main`  
> 기준 구현: `services/rag/`, `rag/`, `backend/app/clients/rag_client.py`, `backend/app/services/chat_service.py`  
> 이 문서는 DDOK BOT 서비스에서 사용자의 질문이 들어온 뒤 Retrieval, Prompt 구성, LLM 답변 생성, Backend 응답까지 실제로 어떻게 처리되는지 설명한다.

---

## 1. 개요

DDOK BOT의 RAG는 사용자가 선택한 공고 안에서 질문과 관련된 근거 Chunk를 찾고, 해당 근거만 이용해 LLM 답변을 생성하는 구조다.

전체 흐름은 다음과 같다.

```text
사용자 질문
  ↓
Backend /chat
  ↓
RAG Service
  ↓
Hybrid Retrieval
  ├─ Vector Search
  └─ BM25 Search
  ↓
RRF
  ↓
상위 Retrieval 결과
  ↓
Generation Context
  ↓
Intent 분류
  ↓
Prompt 조립
  ↓
llama.cpp
  ↓
답변 검증
  ↓
answer + grounded + evidence
  ↓
Backend
  ↓
Frontend
```

RAG의 핵심 원칙은 다음과 같다.

- 사용자가 선택한 `announcement_id` 범위 안에서만 검색한다.
- Vector Search와 BM25 Search를 함께 사용한다.
- 두 검색 결과는 RRF로 결합한다.
- 검색 근거만 LLM Context로 전달한다.
- 질문 유형에 따라 Prompt 규칙을 다르게 적용한다.
- LLM은 llama.cpp의 OpenAI 호환 API를 통해 호출한다.
- 근거를 찾지 못한 경우 답변을 임의 생성하지 않는다.

---

## 2. 실제 서비스 진입점

현재 RAG Service의 실행 진입점은 다음이다.

```text
services/rag/main.py
```

FastAPI Application이 다음 Endpoint를 제공한다.

```http
GET /health

POST /v1/rag/answer
```

실제 질문 처리는:

```text
services/rag/main.py
  ↓
services.rag.service.answer_question()
  ↓
DBRAGPipeline
```

으로 이어진다.

---

## 3. Backend에서 RAG까지의 연결

사용자가 Frontend에서 질문하면 Backend의 Chat API가 요청을 받는다.

현재 흐름:

```text
Frontend
  ↓
Backend Chat API
  ↓
backend/app/services/chat_service.py
  ↓
backend/app/clients/rag_client.py
  ↓ HTTP
POST /v1/rag/answer
  ↓
RAG Service
```

Backend는 기본적으로 HTTP 방식으로 RAG Service를 호출한다.

RAG Runtime 기본값:

```text
rag_http
```

Backend의 RAG Client는 다음 환경설정을 사용한다.

```text
RAG_SERVICE_BASE_URL
RAG_SERVICE_TIMEOUT_SECONDS
```

---

## 4. Chat API 입력

Backend Chat API에서 RAG에 전달하는 핵심 값은 두 가지다.

```text
announcement_id
question
```

예:

```json
{
  "announcement_id": 78,
  "question": "신청기간은 언제인가요?"
}
```

`announcement_id`는 사용자가 현재 선택한 공고를 의미한다.

RAG는 전체 DB를 대상으로 답을 찾는 것이 아니라 **해당 공고 ID 범위 안에서만 Retrieval**한다.

---

## 5. RAG API

실제 RAG Endpoint:

```http
POST /v1/rag/answer
```

Request:

```json
{
  "announcement_id": 78,
  "question": "신청기간은 언제인가요?"
}
```

Request 조건:

```text
announcement_id >= 1
question은 빈 문자열일 수 없음
```

Validation 실패 시:

```text
HTTP 422
RAG_INVALID_REQUEST
```

RAG 내부 처리 중 오류가 발생하면:

```text
HTTP 500
RAG_SERVICE_ERROR
```

형태로 반환한다.

---

## 6. RAG Service 내부 구조

주요 Service 파일:

```text
services/rag/
├── config.py
├── schemas.py
├── service.py
└── main.py
```

주요 역할:

| 파일 | 역할 |
|---|---|
| `main.py` | RAG FastAPI 실행 진입점 |
| `schemas.py` | RAG Request / Response 계약 |
| `service.py` | RAG Pipeline 호출 및 API 응답 구성 |
| `config.py` | PostgreSQL, Embedding, llama.cpp 등 환경설정 |

실제 Retrieval과 Generation 구현은 `rag/` 아래에 있다.

```text
rag/
├── db_pipeline.py
├── models.py
├── retrieval/
└── generation/
```

---

## 7. `DBRAGPipeline`

현재 실제 RAG의 중심 Pipeline은 다음이다.

```text
rag/db_pipeline.py
DBRAGPipeline
```

RAG Service에서 Pipeline은 다음과 같이 생성된다.

```text
DBRAGPipeline.from_database()
```

`services/rag/service.py`는 `_get_pipeline()`에 `lru_cache(maxsize=1)`를 적용한다.

즉 요청마다 Pipeline 객체를 새로 만들지 않고 하나의 Pipeline을 재사용한다.

---

## 8. 실제 질문 처리 흐름

`answer_question()`이 호출되면 다음 순서로 진행된다.

```text
question 검증
  ↓
DBRAGPipeline 확보
  ↓
pipeline.ask()
  ↓
Hybrid Retrieval
  ↓
Generation
  ↓
GeneratedAnswer
  ↓
Evidence 구성
  ↓
RAGAnswerResponse
```

---

# Retrieval

## 9. Retrieval 개요

현재 Retrieval은 다음 두 방식을 함께 사용한다.

```text
Hybrid Retrieval
=
Vector Search
+
BM25 Search
+
RRF
```

두 검색 방식의 목적은 서로 다르다.

```text
Vector Search
→ 질문과 의미적으로 유사한 Chunk 검색

BM25 Search
→ 질문에 등장한 핵심 단어와 직접 일치하는 Chunk 검색
```

공공문서에는 고유 명칭, 수치, 주택형, 조건명 등 정확한 단어 일치가 중요한 경우가 많기 때문에 두 검색 방식을 함께 사용한다.

---

## 10. Retrieval 코드 구조

```text
rag/retrieval/
├── config.py
├── models.py
├── keyword_search.py
└── hybrid_search.py
```

실제 Vector Search는 현재 `DBRAGPipeline.retrieve()`에서 PostgreSQL + pgvector를 이용해 수행한다.

전체 관계:

```text
DBRAGPipeline
├─ Vector Search
│  └─ PostgreSQL + pgvector
│
├─ BM25 Search
│  └─ keyword_search.py
│
└─ Hybrid Search
   └─ hybrid_search.py
```

---

## 11. Query Embedding

Vector Search를 시작하기 전에 사용자의 질문을 Vector로 변환한다.

```text
사용자 질문
  ↓
DBRAGPipeline._embed_query()
  ↓
EmbeddingClient.embed_query()
  ↓
Embedding Service
  ↓
BAAI/bge-m3
  ↓
1024D Dense Vector
```

즉 RAG Service가 BGE-M3 모델을 직접 로드하는 것이 아니다.

공용 Embedding Service를 HTTP로 호출한다.

문서 Chunk와 Query 모두 같은 모델을 사용한다.

```text
BAAI/bge-m3
1024 dimensions
L2 normalized
```

---

## 12. Vector Search

Query Vector가 만들어지면 PostgreSQL의 `embeddings` 테이블과 pgvector를 사용해 유사도 검색을 한다.

핵심 비교:

```text
e.embedding
<=>
query_vector
```

현재 SQL에서는 cosine distance를 이용한 뒤:

```text
1 - cosine distance
```

형태로 similarity 값을 만든다.

즉 질문 Vector와 가까운 Chunk일수록 높은 유사도를 가진다.

---

## 13. Vector Search 범위 제한

Vector Search는 아무 Chunk나 검색하지 않는다.

현재 SQL에서 다음 조건을 확인한다.

```text
현재 Active Collection
현재 announcement_id
Active Chunk Set
Active Processing Run
Chunk status = completed
Embedding status = completed
Embedding model 일치
Embedding dimension = 1024
normalized = true
```

따라서 사용자가 특정 공고를 선택하면 그 공고의 현재 활성 Chunk와 Embedding만 검색 대상이 된다.

---

## 14. Vector Search 기본 개수

현재 Retrieval 기본 설정:

```text
vector_top_k = 20
```

Hybrid Search는 Vector Search에서 우선 최대 20개 후보를 가져온다.

---

## 15. BM25 Search

Keyword Search는 실제로 **Okapi BM25** 알고리즘을 사용한다.

구현 파일:

```text
rag/retrieval/keyword_search.py
```

현재 검색 Corpus는 다음을 우선 사용한다.

```text
Chunk.search_text
```

`search_text`가 비어 있는 예외 데이터에서는:

```text
title + content
```

를 사용한다.

---

## 16. BM25에서 `search_text`를 사용하는 이유

Chunking 단계에서는 하나의 Chunk에 다음 표현을 만든다.

```text
content
search_text
embedding_text
```

BM25는 그중:

```text
search_text
```

를 사용한다.

`search_text`에는 Section 경로, 제목, 검색용 표현 등이 포함될 수 있어 단순 본문만 검색하는 것보다 Keyword Recall을 높일 수 있다.

관계:

```text
Chunking
  ↓
search_text
  ↓
BM25
```

---

## 17. Kiwi 기반 한국어 Tokenization

BM25는 문자열을 단순 공백으로 나누지 않는다.

현재:

```text
kiwipiepy.Kiwi
```

를 사용해 한국어 형태소를 분석한다.

질문과 문서 모두 동일한 Tokenization 방식을 사용한다.

개념:

```text
"신청기간은 언제까지인가요?"
  ↓
Kiwi
  ↓
신청 / 기간 / 언제 ...
```

검색 의미가 낮은 조사, 어미, 문장부호 등은 제거한다.

명사, 동사, 형용사, 숫자 등 의미 있는 형태소는 최대한 유지한다.

---

## 18. BM25가 계산하는 것

BM25는 질문 Token이 각 Chunk에 얼마나 의미 있게 나타나는지를 계산한다.

단순히 단어 등장 횟수만 세는 것은 아니다.

다음 요소를 함께 고려한다.

```text
TF
→ 해당 Chunk에서 단어가 얼마나 등장하는지

IDF
→ 전체 Chunk에서 얼마나 희귀한 단어인지

Document Length
→ Chunk 길이에 따른 보정
```

현재 기본 파라미터:

```text
k1 = 1.5
b = 0.75
```

---

## 19. BM25 검색 범위

BM25도 Vector Search와 동일하게 선택한 `announcement_id` 범위 안에서 검색한다.

또한:

```text
Active Collection
Active Chunk Set
Active Processing Run
completed Chunk
```

조건을 만족하는 Chunk를 대상으로 한다.

따라서 Vector Search와 BM25 Search가 서로 다른 공고를 검색하지 않는다.

---

## 20. BM25 기본 개수

현재 기본값:

```text
bm25_top_k = 20
```

질문과 Keyword 관련성이 높은 최대 20개 후보를 만든다.

---

## 21. Hybrid Search

Hybrid Search 구현:

```text
rag/retrieval/hybrid_search.py
```

흐름:

```text
Query
  ↓
┌───────────────────────────┐
│                           │
│ Vector Search             │ BM25 Search
│ Top 20                    │ Top 20
│                           │
└─────────────┬─────────────┘
              ↓
             RRF
              ↓
        Hybrid Top 20
```

---

## 22. RRF

Vector Search와 BM25는 점수 체계가 서로 다르다.

따라서 원점수를 직접 더하지 않고 **검색 순위**를 이용한다.

현재 사용하는 방식:

```text
Reciprocal Rank Fusion
```

공식:

```text
RRF Score
=
1 / (rrf_k + rank)
```

현재 기본값:

```text
rrf_k = 60
```

같은 Chunk가 Vector와 BM25 양쪽에서 검색되면 두 RRF 점수가 합산된다.

---

## 23. RRF 예시

예를 들어 한 Chunk가:

```text
Vector Rank = 2
BM25 Rank   = 3
```

이라면:

```text
1 / (60 + 2)
+
1 / (60 + 3)
```

으로 결합 점수를 계산한다.

따라서 두 검색 방식 모두에서 높은 순위에 나타나는 Chunk가 상위로 올라갈 가능성이 높다.

---

## 24. Hybrid 결과

현재 기본 설정:

```text
vector_top_k = 20
bm25_top_k   = 20
hybrid_top_k = 20
rrf_k        = 60
```

Hybrid 결과에는 다음과 같은 정보가 유지된다.

```text
chunk_id
Chunk 데이터
Vector 순위
BM25 순위
Fusion 순위
어떤 검색 방식에서 매칭되었는지
```

Generation 단계에서는 최종 Hybrid 순서에 따라 상위 근거를 사용한다.

---

# Generation

## 25. Generation 개요

Retrieval이 끝나면 검색된 Chunk를 그대로 사용자에게 반환하지 않고 LLM 답변 생성에 사용한다.

흐름:

```text
Hybrid Retrieval Results
  ↓
Source Context 생성
  ↓
Context 수 / 길이 제한
  ↓
Intent 분류
  ↓
Prompt 구성
  ↓
llama.cpp
  ↓
답변 후처리
  ↓
답변 검증
  ↓
GeneratedAnswer
```

실제 Generation 진입점:

```text
rag/generation/generator.py
generate_answer()
```

---

## 26. Generation 코드 구조

```text
rag/generation/
├── config.py
├── models.py
├── context_builder.py
├── intent_router.py
├── prompt_builder.py
├── llm_client.py
├── generator.py
└── prompts/
```

역할:

| 파일 | 역할 |
|---|---|
| `generator.py` | 전체 Generation 흐름 |
| `context_builder.py` | Retrieval 결과를 LLM Context로 변환 |
| `intent_router.py` | 질문 유형 분류 |
| `prompt_builder.py` | JSON Prompt 조립 |
| `llm_client.py` | llama.cpp HTTP 호출 |
| `config.py` | Generation 설정 |
| `models.py` | Prompt / Source / Answer 데이터 모델 |
| `prompts/` | 실제 Prompt 규칙 JSON |

---

## 27. LLM Context 생성

Retrieval 결과는 먼저 `SourceContext` 형태로 변환된다.

현재 Generation이 실제로 LLM에 전달하는 근거 개수 기본값:

```text
context_top_k = 5
```

즉 Retrieval에서 최대 20개의 Hybrid 후보를 만들더라도 LLM Context에는 상위 5개를 우선 사용한다.

---

## 28. Context 길이 제한

현재 전체 근거 Content에 대해 기본 길이 제한을 둔다.

```text
llama_max_context_chars = 6000
```

상위 Chunk부터 Context에 넣으며 남은 문자 수가 부족하면 마지막 근거는 잘라서 사용한다.

잘린 경우 내부 Context에 다음 안내가 붙는다.

```text
[이하 내용은 프롬프트 길이 제한으로 생략]
```

이를 통해 검색 결과가 너무 길어 LLM 입력이 과도하게 커지는 것을 제한한다.

---

## 29. Context Block

LLM에 전달되는 각 근거는 개념적으로 다음과 같이 구성된다.

```text
[근거 1]
청크 ID: ...
문서 위치: 공급정보 > 임대조건
문서 형식: hwpx
내용:
...
```

이 내부 정보는 LLM에게 근거의 구분과 문서 위치를 알려주기 위한 것이다.

최종 사용자 답변에는 이러한 내부 정보가 그대로 노출되지 않도록 별도로 검증한다.

---

# Prompt

## 30. Multi-Prompt 구조

현재 Prompt는 하나의 긴 Python 문자열로 고정되어 있지 않다.

JSON Prompt를 역할별로 분리한 뒤 Python에서 조립한다.

구조:

```text
rag/generation/prompts/
├── core.json
├── domains/
│   └── lh.json
├── personas/
│   └── public_user.json
└── intents/
    ├── general.json
    ├── eligibility.json
    ├── schedule.json
    ├── rental_condition.json
    ├── documents.json
    ├── application_method.json
    ├── supply_info.json
    └── location.json
```

Prompt 구성 개념:

```text
Core
+
Domain
+
Persona
+
Intent
+
Retrieval Context
+
User Question
```

---

## 31. Core Prompt

파일:

```text
prompts/core.json
```

서비스 전체에 공통 적용되는 규칙이다.

주요 역할:

```text
Grounding
Accuracy
Output 제한
```

예를 들어:

- 제공된 근거만 사용
- 근거에 없는 내용 추측 금지
- 금액, 날짜, 조건, 수치 임의 변경 금지
- 표의 행과 열 관계 유지
- 서로 다른 대상의 값 혼합 금지
- 내부 시스템 정보 사용자에게 노출 금지

등을 정의한다.

---

## 32. Domain Prompt

현재 Domain:

```text
prompts/domains/lh.json
```

현재 대상 기관:

```text
한국토지주택공사(LH)
```

주요 역할:

- 현재 선택된 공고만 근거로 사용
- 다른 LH 공고나 외부 정보로 보완하지 않음
- 신청 자격, 공급 유형, 주택형 등 조건 구분
- 다른 주택형의 값 혼합 금지
- 사용자 신청 자격을 임의로 최종 판정하지 않음

현재 서비스 구현은 LH 공고문 Domain을 사용한다.

---

## 33. Persona Prompt

파일:

```text
prompts/personas/public_user.json
```

대상:

```text
공공기관 문서를 이용하는 일반 사용자
```

주요 답변 방식:

- 질문과 직접 관련된 내용을 우선
- 쉬운 표현 사용
- 어려운 용어 필요 시 설명
- 자연스럽고 간결한 한국어 사용

즉 정보 정확성 규칙과 사용자에게 보여주는 표현 규칙을 분리해 관리한다.

---

## 34. Intent Prompt

질문 종류에 따라 추가되는 Prompt다.

현재 Intent:

```text
general
eligibility
schedule
rental_condition
documents
application_method
supply_info
location
```

예:

```text
"신청 자격이 어떻게 돼?"
→ eligibility

"신청기간은 언제까지야?"
→ schedule

"보증금이 얼마야?"
→ rental_condition

"어떤 서류가 필요해?"
→ documents
```

Intent별 세부 답변 규칙은 각각의 JSON 파일에서 관리한다.

---

## 35. Intent Router

구현:

```text
rag/generation/intent_router.py
```

현재 분류 방식:

```text
Kiwi 형태소 분석
+
Token Rule
+
자연어 Expression Rule
```

질문을 LLM으로 다시 분류하는 구조가 아니라 규칙 기반으로 Intent를 결정한다.

---

## 36. 복합 질문

현재 Intent Router는 하나의 질문에 여러 Intent가 매칭되는 것을 허용한다.

예:

```text
"신청 자격이랑 신청기간 알려줘"
```

이면 개념적으로:

```text
eligibility
schedule
```

두 Intent가 함께 선택될 수 있다.

Prompt Builder는 선택된 Intent JSON을 모두 불러와 하나의 User Prompt에 결합한다.

아무 Intent도 매칭되지 않으면:

```text
general
```

을 사용한다.

---

## 37. System Prompt 구성

현재 System Prompt는 다음 순서로 조립된다.

```text
Domain
+
Persona
+
Core
```

즉:

```text
LH Domain 규칙
+
일반 사용자 답변 방식
+
전체 Grounding / Accuracy / Output 규칙
```

을 System Message로 전달한다.

---

## 38. User Prompt 구성

User Prompt에는 다음 정보가 들어간다.

```text
질문 유형별 지침
선택한 LH 공고
문서 형식
사용자 질문
LH 공고문 근거
```

개념:

```text
[질문 유형별 지침]
Intent Prompt

[선택한 LH 공고]
announcement_078

[문서 형식]
hwpx

[사용자 질문]
신청기간은 언제인가요?

[LH 공고문 근거]
Retrieval Context
```

---

## 39. 최종 LLM Message

`PromptPayload.to_messages()`는 최종적으로 다음 두 Message를 만든다.

```json
[
  {
    "role": "system",
    "content": "..."
  },
  {
    "role": "user",
    "content": "..."
  }
]
```

즉 JSON Prompt 파일을 llama.cpp에 직접 보내는 것이 아니다.

```text
JSON Prompt 설정
  ↓
prompt_builder.py
  ↓
문자열 조립
  ↓
System Message + User Message
  ↓
llama.cpp
```

구조다.

---

# LLM

## 40. llama.cpp 연결

실제 LLM 호출 파일:

```text
rag/generation/llm_client.py
```

현재 llama.cpp의 OpenAI 호환 Endpoint를 사용한다.

```http
POST /v1/chat/completions
```

RAG Service가 LLM 모델을 Python 내부에서 직접 로드하는 것이 아니라 별도로 실행된 llama-server에 HTTP 요청을 보낸다.

---

## 41. llama.cpp Request

개념적인 Request:

```json
{
  "model": "...",
  "messages": [
    {
      "role": "system",
      "content": "..."
    },
    {
      "role": "user",
      "content": "..."
    }
  ],
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 1024,
  "stream": false
}
```

실제 값은 환경변수 설정에 따라 달라질 수 있다.

---

## 42. Generation 기본 설정

현재 코드 기본값:

```text
LLAMA_BASE_URL
= http://127.0.0.1:8080

temperature
= 0.0

top_p
= 1.0

max_tokens
= 1024

timeout_seconds
= 180

context_top_k
= 5

max_context_chars
= 6000
```

`LLAMA_MODEL` 값은 환경변수로 설정한다.

실제 실행 환경에서는 `.env` 또는 Docker 환경변수를 기준으로 한다.

---

## 43. 출력 Token 제한 감지

llama.cpp Response의:

```text
finish_reason
```

을 확인한다.

다음 값이면:

```text
finish_reason = length
```

답변이 최대 Token 제한에 도달해 잘린 것으로 판단하고 오류를 발생시킨다.

이 경우 확인 대상은:

```text
LLAMA_MAX_TOKENS
llama-server Context Size
```

이다.

---

## 44. 답변 후처리

LLM이 답변에 다음과 같은 내부 근거 Marker를 생성하면:

```text
[근거 1]
[근거 2]
[출처 1]
```

`remove_source_markers()`에서 최종 사용자 답변 전에 제거한다.

실제 Evidence 정보는 별도의 응답 데이터로 유지한다.

---

## 45. 답변 품질 검증

LLM 생성 후 `validate_korean_answer()`에서 최종 답변을 검사한다.

대표 검증:

```text
빈 답변 금지
중국어/일본어 문자 혼입 방지
Prompt 내부 Marker 노출 방지
Chunk ID 노출 방지
검색 내부 정보 노출 방지
System/User 역할 문자열 노출 방지
```

즉 LLM이 내부 RAG Context를 그대로 사용자에게 출력하지 않도록 방어한다.

---

## 46. Generation 재시도

첫 번째 생성 답변이 품질 검증을 통과하지 못하면 한 번 다시 생성한다.

재시도 시 System Prompt에 다음 취지의 규칙을 추가한다.

```text
자연스러운 한국어 답변 본문만 출력
내부 Prompt 정보 출력 금지
Chunk ID 출력 금지
내부 검색 정보 출력 금지
```

재시도 결과도 검증에 실패하면 사용자에게 안정적인 오류 안내 문장을 반환한다.

---

# Response

## 47. RAG Response

현재 RAG API Response:

```text
result
answer
grounded
evidence
```

예:

```json
{
  "result": "grounded",
  "answer": "신청기간은 ...입니다.",
  "grounded": true,
  "evidence": [
    {
      "chunk_id": "...",
      "section_title": "신청일정",
      "content": "...",
      "score": 0.0
    }
  ]
}
```

`evidence`의 실제 값은 검색 결과에 따라 달라진다.

---

## 48. `result` 상태

현재 세 가지 상태를 사용한다.

```text
grounded
no_evidence
unsupported
```

### `grounded`

근거가 존재하고 정상적인 답변이 생성된 경우.

### `no_evidence`

선택한 공고에서 검색 가능한 근거 자체를 찾지 못한 경우.

이 경우:

```text
grounded = false
evidence = []
```

이며 기본 답변:

```text
제공된 LH 공고문 근거에서 확인할 수 없습니다.
```

를 반환한다.

### `unsupported`

Evidence는 존재하지만 최종 답변을 Grounded 답변으로 판단하지 못한 경우다.

---

## 49. Evidence

RAG Service는 Generation에 사용된 Source를 기반으로 Evidence를 만든다.

대표 정보:

```text
chunk_id
section_title
content
score
```

`section_title`은 우선:

```text
section_path
```

를 `>`로 연결해서 사용한다.

Section Path가 없으면 Chunk Title을 사용한다.

---

## 50. Backend Response 변환

Backend는 RAG Service Response를 받아 사용자용 `ChatResponse`로 변환한다.

흐름:

```text
RAGAnswerResponse
  ↓
backend/app/clients/rag_client.py
  ↓
backend/app/services/chat_service.py
  ↓
ChatResponse
```

Backend가 최종적으로 전달하는 주요 값:

```text
answer
grounded
evidence
```

RAG 내부의 `result`는 Backend Client에서는 검증하지만 사용자 Chat Response의 핵심 반환 값은 `answer`, `grounded`, `evidence`다.

---

## 51. 전체 서비스 흐름

```text
Frontend
  ↓
POST Backend /chat
  ↓
announcement_id + question
  ↓
Backend Chat Service
  ↓
RAG Client
  ↓ HTTP
POST /v1/rag/answer
  ↓
RAG Service
  ↓
DBRAGPipeline
  ↓
────────────────────────────────
Hybrid Retrieval
────────────────────────────────
  ↓
Query Embedding
  ↓
Embedding Service
  ↓
BGE-M3 1024D
  ↓
PostgreSQL + pgvector Vector Search
  ↓
Vector Top 20

동시에

PostgreSQL Active Chunks
  ↓
Kiwi Tokenization
  ↓
BM25 Search
  ↓
BM25 Top 20
────────────────────────────────
  ↓
RRF
  ↓
Hybrid Top 20
  ↓
Generation Context Top 5
  ↓
Intent Router
  ↓
Core + Domain + Persona + Intent
  ↓
System Prompt + User Prompt
  ↓
llama.cpp
/v1/chat/completions
  ↓
답변 후처리
  ↓
한국어 / 내부정보 노출 검증
  ↓
필요 시 1회 재생성
  ↓
answer + grounded + evidence
  ↓
Backend
  ↓
Frontend
```

---

## 52. 주요 환경설정

RAG Service:

```text
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD

EMBEDDING_SERVICE_URL
EMBEDDING_MODEL_NAME
EMBEDDING_MODEL_PATH

LLAMA_BASE_URL
LLAMA_MODEL
LLAMA_TEMPERATURE
LLAMA_TOP_P
LLAMA_MAX_TOKENS
LLAMA_TIMEOUT_SECONDS
LLAMA_CONTEXT_TOP_K
LLAMA_MAX_CONTEXT_CHARS

RAG_DB_TOP_K
MVP_DOCUMENT_FORMAT
```

Backend → RAG 연결:

```text
RAG_SERVICE_BASE_URL
RAG_SERVICE_TIMEOUT_SECONDS
RAG_RUNTIME
```

---

## 53. 핵심 정리

현재 DDOK BOT RAG는 다음과 같이 정리할 수 있다.

```text
RAG Service 진입점
= services/rag/main.py

RAG API
= POST /v1/rag/answer

중심 Pipeline
= DBRAGPipeline

검색 범위
= 사용자가 선택한 announcement_id

Query Embedding
= Embedding Service / BAAI/bge-m3 / 1024D

Retrieval
= Vector Search + BM25

Vector 저장/검색
= PostgreSQL + pgvector

BM25 Tokenizer
= Kiwi

검색 결과 결합
= RRF

Retrieval 후보
= Vector 20 + BM25 20 → Hybrid 20

LLM Context
= 상위 5개

Prompt
= Core + Domain + Persona + Intent + Context + Question

Intent 분류
= Kiwi + Rule

Generation
= llama.cpp /v1/chat/completions

최종 응답
= answer + grounded + evidence
```

DDOK BOT의 RAG 핵심은 **선택한 공고 범위 안에서 의미 검색과 키워드 검색을 함께 수행하고, 검색된 근거만 Prompt에 넣어 공고문 기반 답변을 생성하는 것**이다.

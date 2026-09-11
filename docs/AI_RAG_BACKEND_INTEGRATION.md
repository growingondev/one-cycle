# AI / RAG Backend Integration Status

> 2026-08-25 기준 AI/RAG와 Backend 통합 상태, LLM 교체 대응 작업 및 남은 검증 항목을 정리한 문서입니다.
>
> 이 문서는 현재 구현 상태를 인수인계하거나 AWS 전체 Pipeline 통합을 이어서 진행할 때 사용합니다.

---

# 1. 현재 통합 상태 요약

| 영역 | 상태 | 비고 |
|---|---|---|
| Chunk → Embedding 입력 계약 | 완료 | 샘플 5개 연결 검증 PASS |
| Embedding → DB Persistence | 완료 | Chunk 5개 / Embedding 5개 / 1024차원 / 1:1 PASS |
| Vector Retrieval | 완료 | BGE-M3 Query Embedding + pgvector 검색 PASS |
| Keyword Retrieval | 완료 | PostgreSQL Keyword Search PASS |
| Hybrid Retrieval | 완료 | Vector + Keyword + RRF PASS |
| Reranker | 보류 | 중간발표 이후 성능 고도화 단계에서 선정/적용 |
| Generation 연결 코드 | 완료 | Hybrid Context → Generation 구조 연결 |
| Generation 실제 llama.cpp 통합 | 부분 검증 | AWS llama.cpp에서 Gemma 모델 로드 및 `/v1/models`, `/v1/chat/completions` 직접 호출 PASS. 전체 Chat API E2E는 추가 확인 필요 |
| Chunking ErrorLog | 완료 | 실제 DB 기록 PASS |
| Embedding ErrorLog | 완료 | 실제 DB 기록 PASS, 중복 1건 확인 |
| Retrieval ErrorLog | 완료 | 실제 DB 기록 PASS |
| Generation/LLM ErrorLog | 코드 연결 | 실제 DB 로그 검증은 전체 Chat API 통합 시 확인 |
| publish_collection_run | Backend 구현 확인 | 전체 Pipeline orchestration에서 호출 필요 |

---

# 2. Persistence 계약 검증

테스트에서는 실제 전체 데이터가 아니라 앞 5개 Chunk/Embedding만 사용했습니다.

중요:

```text
LIMIT 5는 테스트 범위를 줄이기 위한 것일 뿐
운영 Pipeline 계약을 5개로 제한하는 변경이 아닙니다.
```

검증 결과:

```text
원본 Chunk: 5
metadata: 5
vectors: (5, 1024)

Chunk ↔ Metadata ID: PASS
L2 norm: 약 1.0
NaN: 0
Inf: 0
```

DB Persistence 검증:

```text
ProcessingRun 생성      PASS
DocumentStructure 생성  PASS
ChunkSet 생성           PASS
Chunk 5개 저장          PASS
Embedding 5개 저장      PASS
Vector dimension 1024   PASS
Chunk ↔ Embedding 1:1   PASS
```

초기 Persistence 테스트는 rollback으로 검증했고,
Retrieval 테스트에서는 임시 commit 후 테스트가 끝나면 정리했습니다.

운영용 `pipeline_persistence.py`의 전체 데이터 처리 계약을 LIMIT 5에 맞게 수정하지 않습니다.

---

# 3. Retrieval 현재 구조

현재 구현/검증한 검색 흐름:

```text
사용자 질문
    ↓
BGE-M3 Query Embedding
    ↓
┌─────────────────────┐
│                     │
▼                     ▼
pgvector           Keyword Search
Vector Search      PostgreSQL
│                     │
└──────────┬──────────┘
           ↓
       RRF Fusion
           ↓
   Hybrid Retrieval
           ↓
   Generation Context
```

테스트 질문:

```text
계약금
```

Hybrid 결과에서 다음 Chunk가 1위로 검색되는 것을 확인했습니다.

```text
청주지북 B1블록 공공분양주택 잔여세대 선착순 동호지정 입주자모집공고
[계약금 1,000만원 정액제]
```

1위 결과:

```text
vector_rank: 1
keyword_rank: 1
matched_by: keyword, pgvector
```

따라서 Vector와 Keyword 결과를 RRF로 결합하는 기본 Hybrid Retrieval 동작은 확인되었습니다.

---

# 4. Reranker 현재 정책

현재 중간발표 범위에서는 Reranker를 사용하지 않습니다.

이유:

```text
Hybrid Retrieval까지 기본 검색 흐름 검증 완료
Reranker는 검색 정확도 고도화 단계
모델 선정 및 추가 성능 평가 필요
```

따라서 현재:

```text
Hybrid Retrieval
→ Generation
```

으로 연결합니다.

중간발표 이후:

```text
Hybrid Retrieval
→ Reranker
→ Generation
```

구조를 검토합니다.

QLoRA 역시 현재 필수 Pipeline 단계가 아닙니다.

현재 Generation은 시스템 프롬프트 기반으로 먼저 검증하고,
QLoRA는 중간발표 이후 Generation 품질 고도화 단계에서 검토합니다.

---

# 5. Generation 현재 상태

Generation은 Retrieval 결과를 Context로 조립한 뒤 llama.cpp의 OpenAI 호환 Chat Completion API를 호출하는 구조입니다.

현재 흐름:

```text
Retrieval
    ↓
Retrieved Chunks
    ↓
Context Builder
    ↓
System Prompt + Context + User Question
    ↓
rag/generation/llm_client.py
    ↓
POST /v1/chat/completions
    ↓
llama.cpp
    ↓
현재 선택된 GGUF LLM
    ↓
Answer
```

기존 코드에는 Qwen 이름이 일부 직접 들어가 있었지만,
성능 테스트 중 모델을 반복 교체할 수 있도록 Generation 코드를 특정 LLM에 종속되지 않는 구조로 수정했습니다.

현재 주요 변경 사항:

```text
rag/generation/config.py

Qwen 전용 설명 제거
LLAMA_MODEL 기본값에서 특정 모델명 제거

LLAMA_TEMPERATURE
LLAMA_TOP_P
LLAMA_MAX_TOKENS
LLAMA_CONTEXT_TOP_K
LLAMA_MAX_CONTEXT_CHARS

환경변수 기반 설정 지원
```

따라서 향후 Gemma → Qwen → 다른 GGUF LLM으로 성능 테스트 모델이 변경되어도
Python Source Code의 Model 이름을 매번 수정하지 않습니다.

변경 대상:

```text
1. llama-server에서 로드할 GGUF 파일
2. llama-server의 --alias
3. .env의 LLAMA_MODEL
```

핵심 규칙:

```text
llama-server --alias
=
LLAMA_MODEL
```

현재 AWS Gemma 테스트에서는:

```text
Model
/home/ubuntu/ddokbot/models/llm/gemma4-12b/gemma-4-12B-it-Q4_0.gguf

Alias
gemma

Context Size
8192
```

로 llama.cpp Server가 정상 실행되는 것을 확인했습니다.

`GET /v1/models`에서:

```text
model id: gemma
n_ctx: 8192
```

를 확인했습니다.

또한 `POST /v1/chat/completions` 직접 호출에서 한국어 응답 생성과:

```text
finish_reason: stop
```

을 확인했습니다.

초기 작은 `max_tokens` 테스트에서는 Gemma의 reasoning 출력 때문에 실제 `content`가 생성되기 전에:

```text
finish_reason: length
content: ""
```

상태가 발생했습니다.

출력 Token 한도를 늘린 뒤 정상 응답을 확인했으며,
현재 성능 테스트 기준:

```env
LLAMA_MAX_TOKENS=1024
```

로 조정했습니다.

Generation Context 길이 역시 환경변수로 조정할 수 있습니다.

```text
LLAMA_CONTEXT_TOP_K
→ Generation에 사용할 최대 Retrieval 결과 수

LLAMA_MAX_CONTEXT_CHARS
→ Prompt에 포함할 Retrieval 근거 전체 문자 수 제한
```

`LLAMA_MAX_CONTEXT_CHARS`는 각 Chunk별 제한이 아니라
선택된 Source들의 전체 Content에 적용되는 총량 제한으로 수정했습니다.

예:

```text
LLAMA_CONTEXT_TOP_K=5
LLAMA_MAX_CONTEXT_CHARS=6000
```

이면 최대 5개 Source를 순서대로 사용하되,
Prompt에 들어가는 Retrieval Content 전체 길이는 약 6000자를 넘지 않도록 구성합니다.

Generation Prompt는 기존 LH 공고문 근거 기반 정책을 유지합니다.

```text
선택 공고 근거만 사용
근거가 없으면 추측 금지
한국어 답변
수치/조건 임의 변경 금지
근거 번호 및 내부 검색 정보 사용자 답변에 노출 금지
```

현재 llama.cpp 단독 Generation 호출까지는 AWS에서 확인했습니다.

남은 최종 검증:

```text
FastAPI /api/chat
    ↓
rag.service:answer_question
    ↓
DB Retrieval
    ↓
Generation
    ↓
Gemma llama.cpp
    ↓
ChatResponse
```

전체 End-to-End 흐름입니다.

---

# 6. Backend 공통 ErrorLog 연결

Backend 공통 진입점:

```text
record_error(...)
```

를 AI/RAG 단계의 오류 경계에 연결했습니다.

원칙:

```text
하위 함수에서 오류
    ↓
상위 Stage로 raise
    ↓
Stage 외부 진입점에서 record_error() 1회
```

동일 예외를 여러 계층에서 중복 저장하지 않습니다.

## 6.1 Chunking

대상:

```text
pipeline/chunking/run_chunking.py
```

실제 오류 입력:

```text
sections must be an array
```

DB 확인:

```text
error_type: chunking
stage: chunking
error_code: ValueError
status: unresolved
stack_trace: 존재
```

상태:

```text
PASS
```

## 6.2 Embedding

대상:

```text
pipeline/embedding/run_embeddings.py
```

실제 오류 입력:

```text
chunks[0].embedding_text는 문자열이어야 합니다.
```

DB 확인:

```text
error_type: embedding
stage: embedding
error_code: ChunkLoadError
status: unresolved
stack_trace: 존재
```

같은 예외가 중복 기록되지 않고 1건만 저장되는 것도 확인했습니다.

상태:

```text
PASS
```

## 6.3 Retrieval

대상:

```text
rag/retrieval/hybrid_search.py
```

의도적으로 빈 질문을 전달했습니다.

DB 확인:

```text
error_type: rag
stage: retrieval
error_code: HybridSearchError
message: 검색 질문이 비어 있습니다.
status: unresolved
collection_run_id: 1
announcement_id: 1
stack_trace: 존재
```

Backend 관계 추적으로 `collection_run_id`까지 연결되는 것을 확인했습니다.

상태:

```text
PASS
```

## 6.4 Generation / LLM

대상:

```text
rag/generation/generator.py
```

연결 정책:

```text
error_type: llm
stage: generation
```

Generation 외부 진입점에서 오류를 한 번 기록하도록 연결했습니다.

현재 llama.cpp Server 자체와 Chat Completion 직접 호출은 AWS에서 정상 동작을 확인했습니다.

다만 Backend Chat API 전체 흐름에서 의도적으로 Generation 오류를 발생시켜
공통 ErrorLog DB에 실제 1건이 기록되는 통합 검증은 아직 남아 있습니다.

상태:

```text
Generation ErrorLog 코드 연결 완료
llama.cpp 직접 호출 PASS
실제 DB ErrorLog 통합 검증은 Chat API E2E 단계에서 확인
```

---

# 7. publish_collection_run 확인 결과

Backend 구현:

```text
backend/app/services/collection_publish_service.py
```

`publish_collection_run(collection_run_id)`은 단순 active 변경 함수가 아닙니다.

Publish 전에 다음을 검증합니다.

```text
CollectionRun.status == success
실패 Announcement == 0
CollectionRun 건수와 실제 Announcement 수 일치

모든 Announcement에 Document 존재
모든 Document download_status == completed

모든 Document에 active ProcessingRun 존재
ProcessingRun.execution_status == succeeded
ProcessingRun.verification_status == pass

active ChunkSet 존재
ChunkSet.status == completed
ChunkSet.chunk_count와 실제 Chunk 수 일치
모든 Chunk status == completed

모든 Chunk에 RAG용 Embedding 존재
Embedding.model_name == 현재 Retrieval 모델
Embedding.dimension == 1024
Embedding.normalized == true
Embedding.status == completed
```

모든 검증을 통과하면:

```text
system_state.active_collection_run_id
```

를 새 CollectionRun으로 변경합니다.

---

# 8. publish 호출 주체

AI/RAG의 개별 Stage에서 직접 호출하지 않습니다.

잘못된 예:

```text
run_embeddings.py
    ↓
publish_collection_run()
```

이 방식은 한 Document의 Embedding이 끝난 시점과
Collection 전체 처리가 끝난 시점을 혼동할 수 있습니다.

권장 구조:

```text
Collection 전체 처리 시작
    ↓
각 Announcement / Document 처리
    ↓
Chunking
    ↓
Embedding
    ↓
Persistence
    ↓
모든 대상 처리 성공 확인
    ↓
CollectionRun 상태/건수 최종 반영
    ↓
publish_collection_run(collection_run_id)
```

따라서 호출 주체는:

```text
Backend 전체 Pipeline Orchestration
```

이 적절합니다.

현재 AI/RAG에서 별도 publish 호출 코드를 추가하지 않습니다.

---

# 9. AWS 전체 통합 시 반드시 확인할 것

```text
[ ] PostgreSQL + pgvector 정상
[ ] Alembic migration 적용
[ ] BGE-M3 로드
[ ] 전체 Chunk 생성
[ ] 전체 Embedding 생성
[ ] Persistence 성공
[ ] Chunk ↔ Embedding 전체 1:1
[ ] ProcessingRun / ChunkSet 상태 정상
[ ] Hybrid Retrieval 정상
[x] llama.cpp :8080 Gemma 실행 확인
[x] `/v1/models` Model Alias 확인
[x] `/v1/chat/completions` 직접 Generation 응답 확인
[ ] FastAPI `/api/chat` 기준 Generation End-to-End 확인
[ ] Generation/LLM ErrorLog 실제 DB 기록 확인
[ ] Collection 전체 성공 상태 반영
[ ] publish_collection_run() 호출
[ ] system_state.active_collection_run_id 변경 확인
[ ] publish 이후 Runtime RAG가 새 active dataset 검색
```

---

# 10. 현재 하지 말아야 할 것

```text
LIMIT 5 테스트 때문에 운영 Persistence를 5개 기준으로 수정
Retrieval 테스트 파일을 Runtime 코드로 사용
Reranker를 현재 필수 단계로 강제
QLoRA를 현재 Pipeline 필수 단계로 추가
각 하위 함수마다 record_error()를 중복 호출
Embedding 완료 직후 개별 Stage에서 publish 호출
llama.cpp 직접 호출 PASS만으로 FastAPI Chat API 전체 E2E까지 PASS했다고 기록
```

---

# 11. 다음 작업

현재 우선 작업:

```text
1. .env / .env.example에 신규 Generation 환경변수 반영
2. AWS Runtime .env의 LLAMA_MODEL과 llama-server --alias 일치 확인
3. FastAPI /api/chat End-to-End 실행
4. 실제 DB Retrieval → Generation → ChatResponse 확인
5. no-evidence와 실제 Generation 실패 응답 분리 동작 확인
6. Generation/LLM ErrorLog 실제 DB 기록 확인
7. 동일 평가셋으로 Gemma 성능 측정
```

성능 테스트 시 Model 교체 절차:

```text
1. 테스트할 GGUF Model 준비
2. 기존 llama-server 종료
3. 새 GGUF Model로 llama-server 실행
4. --alias 지정
5. LLAMA_MODEL을 동일 Alias로 설정
6. /v1/models 확인
7. /v1/chat/completions Smoke Test
8. RAG / Chat API 평가 실행
```

이 과정에서는 Model 이름 변경을 위해
`rag/generation/config.py`, `generator.py`, `llm_client.py`를 반복 수정하지 않습니다.

성능 고도화:

```text
1. Retrieval 평가
2. Reranker 모델 선정 및 적용 검토
3. Hybrid 파라미터/RRF 조정
4. Generation Prompt 개선
5. 필요 시 Generation Parameter 비교
6. QLoRA 적용 여부 검토
7. 동일 평가셋으로 모델별/설정별 성능 비교
```

---

# 12. 핵심 인수인계 요약

```text
Document Pipeline
→ Chunk/Embedding 계약 검증 완료

Persistence
→ 샘플 DB 저장 검증 완료

Retrieval
→ Vector PASS
→ Keyword PASS
→ Hybrid + RRF PASS

Reranker
→ 현재 제외, 성능 고도화 단계에서 검토

Generation
→ Retrieval Context 연결 완료
→ 특정 Qwen 이름에 종속되지 않도록 설정 구조 수정
→ Model 및 주요 Generation Parameter 환경변수화
→ Context 전체 문자 수 제한 구조 적용
→ AWS Gemma llama.cpp 실행 PASS
→ /v1/models PASS
→ /v1/chat/completions 직접 호출 PASS
→ LLAMA_MAX_TOKENS=1024 테스트
→ FastAPI /api/chat 전체 E2E는 추가 확인

Model 교체
→ Python Source Code의 모델명 직접 수정 금지
→ GGUF 파일 변경
→ llama-server --alias 변경
→ LLAMA_MODEL을 동일 Alias로 변경

No Evidence
→ 검색 결과 없음과 실제 LLM 생성 실패를 구분하는 구조 적용
→ 검색 결과 없음은 grounded=false / evidence=[] / no-answer 응답으로 처리
→ 실제 API End-to-End 재검증 필요

ErrorLog
→ Chunking PASS
→ Embedding PASS
→ Retrieval PASS
→ Generation 코드 연결
→ Generation 실제 DB 로그는 Chat API E2E에서 확인

Publish
→ Backend 함수 구현/검증 조건 확인
→ AI/RAG 개별 단계가 아니라 전체 Pipeline orchestration에서 호출
```

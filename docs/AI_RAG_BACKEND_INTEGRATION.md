# AI / RAG Backend Integration Status

> 2026-08-19 기준 AI/RAG와 Backend 통합 검증 및 남은 작업을 정리한 문서입니다.
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
| Generation 실제 llama.cpp 통합 | 미검증 | 로컬 llama.cpp 미실행으로 AWS에서 최종 확인 필요 |
| Chunking ErrorLog | 완료 | 실제 DB 기록 PASS |
| Embedding ErrorLog | 완료 | 실제 DB 기록 PASS, 중복 1건 확인 |
| Retrieval ErrorLog | 완료 | 실제 DB 기록 PASS |
| Generation/LLM ErrorLog | 코드 연결 | 실제 DB 로그 테스트는 AWS 통합 시 확인 |
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

Generation 코드와 Retrieval 결과 연결은 구성했습니다.

목표 흐름:

```text
Hybrid Retrieval
    ↓
Retrieved Chunks
    ↓
Context Builder
    ↓
System Prompt + Context + User Question
    ↓
llama.cpp
    ↓
Qwen
    ↓
Answer
```

로컬 테스트에서는 Retrieval과 Context 생성까지 정상 진행했습니다.

마지막 llama.cpp 호출에서는:

```text
Connection refused
http://127.0.0.1:8080/v1/chat/completions
```

이 발생했습니다.

이는 당시 로컬 Mac에서 llama.cpp server가 실행되고 있지 않아 발생한 연결 오류입니다.

따라서 현재 판단:

```text
Retrieval → Generation 입력 연결: 확인
실제 LLM 응답 생성: AWS llama.cpp 환경에서 최종 검증 필요
```

Generation 전체가 실제 정상 동작한다고 확정하지 않습니다.

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

다만 실제 DB 기록 테스트를 위해 기존 Generation 테스트 환경을 다시 복구해야 했기 때문에
현재 로컬에서는 실테스트를 생략했습니다.

상태:

```text
코드 연결 완료
실제 DB 로그 검증은 AWS 전체 통합 시 수행
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
[ ] llama.cpp :8080 실행
[ ] Generation 실제 응답 정상
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
Generation 미검증 상태를 실제 LLM 응답까지 PASS했다고 기록
```

---

# 11. 다음 작업

중간발표 전:

```text
1. 현재 Hybrid Retrieval 구조 유지
2. AWS llama.cpp 환경에서 Generation 전체 연결
3. 실제 Pipeline 전체 데이터 Persistence
4. Backend orchestration에서 Collection publish 연결
5. 사용자 Chat API End-to-End 확인
```

중간발표 후 성능 고도화:

```text
1. Retrieval 평가
2. Reranker 모델 선정 및 적용 검토
3. Hybrid 파라미터/RRF 조정
4. Generation Prompt 개선
5. QLoRA 적용 여부 검토
6. 동일 평가셋으로 전후 성능 비교
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
→ 현재 제외, 발표 이후 고도화

Generation
→ Retrieval Context 연결 완료
→ 실제 llama.cpp 응답은 AWS에서 최종 검증

ErrorLog
→ Chunking PASS
→ Embedding PASS
→ Retrieval PASS
→ Generation 코드 연결, 실로그는 AWS에서 확인

Publish
→ Backend 함수 구현/검증 조건 확인
→ AI/RAG 개별 단계가 아니라 전체 Pipeline orchestration에서 호출
```

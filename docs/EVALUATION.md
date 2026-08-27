# DDOKBOT RAG Evaluation

>
> 프로젝트를 처음 보는 개발자가 다음 내용을 이해하고 그대로 이어서 작업할 수 있는 수준을 목표로 합니다.
>
> - 무엇을 평가하는지
> - 평가 문서와 질문셋은 어디에 있는지
> - 평가 전용 DB를 왜 사용하는지
> - 실제 서비스 RAG 경로를 어떻게 평가에 재사용하는지
> - `evaluate_rag.py`와 `evaluate_metrics.py`가 각각 무엇을 하는지
> - Retrieval / Generation Metric을 어떻게 해석하는지
> - 문제가 생겼을 때 어느 단계부터 확인해야 하는지


# 1. 평가 파트 개요

DDOKBOT Evaluation은 코드나 모델을 변경했을 때 RAG 성능이 실제로 좋아졌는지 동일한 조건에서 반복 측정하는 영역입니다.

평가는 크게 두 단계로 나눕니다.
```text
Retrieval
→ 정답을 생성하는 데 필요한 원문 근거를 검색했는가?

Generation
→ 검색된 근거를 바탕으로 정확한 답변을 생성했는가?
```
현재 평가의 핵심 원칙은 **평가용 별도 검색기를 주 경로로 사용하지 않고, 평가 전용 DB에 고정 문서를 적재한 뒤 실제 서비스와 동일한 문서처리·DB·Hybrid Retrieval·Generation 경로를 재사용하는 것**입니다.

전체 흐름:
```text
고정 평가 HWP/HWPX
        ↓
평가 전용 DB
        ↓
실제 Document Pipeline
        ↓
Chunk + BGE-M3 Embedding
        ↓
PostgreSQL + pgvector
        ↓
Vector Search + Keyword Search
        ↓
RRF
        ↓
Generation LLM
        ↓
POST /api/chat
        ↓
Answer + Evidence 저장
        ↓
Recall@1 / @3 / @5
        +
RAGAS
        ↓
RUN 비교
        ↓
Failure Analysis
```

# 2. 왜 평가 기능이 필요한가

RAG는 다음 요소 중 하나만 바뀌어도 결과가 달라질 수 있습니다.
```text
Parser
Normalizer
Structure
Chunking
Embedding
Vector Search
Keyword Search
RRF
Prompt
Generation LLM
```
몇 개 질문을 직접 입력해보고 체감으로 판단하면 코드 변경의 효과를 객관적으로 비교하기 어렵습니다.

평가에서는 가능한 한 다음을 고정합니다.
```text
같은 원본 문서
같은 질문셋
같은 평가 기준
```
그 상태에서 한 번에 한 요소씩 변경합니다.

예:
```text
RUN_001
기존 Retrieval + Qwen

RUN_002
Hybrid Retrieval + Qwen

RUN_003
Hybrid Retrieval + Gemma
```
이렇게 해야 검색 개선 효과와 Generation 모델 변경 효과를 구분할 수 있습니다.


# 3. 전체 서비스에서의 위치

실제 서비스:
```text
LH 공고
→ Document Processing
→ DB
→ Retrieval
→ Generation
→ /api/chat
→ 사용자
```
평가:
```text
고정 평가 공고
→ Evaluation DB
→ 동일 Document Processing
→ 동일 DB Schema
→ 동일 Retrieval
→ 동일 Generation
→ 동일 /api/chat
→ 평가 스크립트
```
즉 평가 파트는 사용자 기능이 아니라 **서비스 품질을 검증하는 개발/검증 영역**입니다.


# 4. 관련 문서

현재 평가 구조를 이해할 때 참고할 문서는 다음과 같습니다.

| 문서 | 역할 |
| --- | --- |
| `docs/EVALUATION.md` | 평가 전체 구조와 실행 방법 |
| `docs/BACKEND_DB_EVALUATION_WORKFLOW.md` | 평가 DB 생성, 문서 등록, Pipeline 처리, Publish |
| `docs/AI_RAG_BACKEND_INTEGRATION.md` | Backend와 RAG 연결 |
| `docs/RAG_RETRIEVAL_GENERATION_HANDOVER.md` | Hybrid Retrieval과 Generation 구조 |

이 문서는 전체 흐름을 설명하고, 세부 구현은 위 문서와 실제 코드에서 확인합니다.


# 5. 주요 코드 구조
```text
evaluation/
├── datasets/
│   ├── GC_FINAL_V1.xlsx
│   └── BD_FINAL_V1.xlsx
│
├── source_documents/
│   ├── DOC_GC_001/
│   └── DOC_BD_001/
│
├── results/
├── evaluate_rag.py
├── evaluate_metrics.py
├── evaluate_rag_fixed.py
├── prepare_fixed_documents.py
│
└── fixed_rag/
    ├── pipeline.py
    ├── retriever.py
    └── service.py
```
평가 DB 관련 코드:
```text
backend/app/services/
├── evaluation_service.py
└── evaluation_pipeline_service.py

backend/scripts/evaluation/
├── create_evaluation_db.py
└── drop_evaluation_db.py

tests/backend/
└── test_evaluation_services.py
```

# 6. 평가 대상 문서와 Dataset

현재 고정 평가 원본:
```text
DOC_GC_001
DOC_BD_001
```
Dataset:
```text
evaluation/datasets/GC_FINAL_V1.xlsx
evaluation/datasets/BD_FINAL_V1.xlsx
```
Dataset Code:
```text
GC
→ 고창율계

BD
→ 서울 번동3
```
평가 문서를 고정하는 이유는 RUN마다 원본 문서가 바뀌면 결과 차이가 코드 때문인지 문서 변경 때문인지 구분하기 어렵기 때문입니다.


# 7. 질문 구성

현재 서울 번동3 최종 일반화 평가용 질문은 총 70문항입니다.

| 구분 | 문항 수 | 목적 |
| --- | ---: | --- |
| `frequent` | 25 | 일정·자격·소득·자산·임대조건 등 직접 질문 |
| `variant` | 12 | 같은 사실의 자연어·부정형·표현 변형 |
| `condition` | 7 | 조건을 기준과 비교해 신청 가능 여부 판단 |
| `hard` | 8 | 비교·다중정보·간단한 추론 |
| `colloquial` | 3 | 구어체·키워드형 질문 |
| `unanswerable` | 5 | 문서에 없는 정보에 대한 답변 제한 확인 |
| `robustness` | 10 | 입력 변형에 대한 견고성 확인 |
| **합계** | **70** | 서울 번동3 최종 일반화 평가 |

이 구분은 단순 난이도보다 **어떤 사용자 입력 형태에서 성능이 떨어지는지 분석하기 위한 평가 그룹**입니다.

---

## 7.1 frequent

사용자가 가장 자주 묻는 기본 정보입니다.

예:
```text
신청 기간은 언제인가요?
소득 기준은 어떻게 되나요?
임대보증금은 얼마인가요?
```
---

## 7.2 variant

같은 사실을 다른 표현으로 질문합니다.

예:
```text
신청 기간은 언제인가요?
접수는 언제부터 받아요?
9월에도 신청할 수 있어?
```
목적은 표현이 달라도 같은 근거를 검색하는지 확인하는 것입니다.

---

## 7.3 condition

사용자의 조건이나 특정 값을 공고 기준과 비교합니다.

예:
```text
총자산이 3억이면 신청 가능한가요?
자동차가액이 이 금액을 넘으면 신청 못 하나요?
```
처리 개념:
```text
사용자 조건
→ 공고 기준 검색
→ 조건 비교
→ 답변
```
---

## 7.4 hard

여러 정보를 함께 확인하거나 비교해야 하는 질문입니다.

예:
```text
신청일부터 발표일까지 주요 일정을 순서대로 알려주세요.
두 공급 유형의 임대조건 차이는 무엇인가요?
```
정답 근거가 여러 Chunk에 나뉠 수 있습니다.

---

## 7.5 colloquial

실제 사용자처럼 짧고 구어체로 질문합니다.

예:
```text
보증금 얼마야?
접수 언제?
나도 신청 가능?
```
---

## 7.6 unanswerable

공고문에 없는 정보를 일부러 질문합니다.

목적:
```text
문서에 없는 내용을 LLM이 만들어내지 않는가?
```
기대 동작:
```text
공고문에서 확인할 수 없습니다.
해당 정보가 명시되어 있지 않습니다.
```
---

## 7.7 robustness

실제 사용자는 항상 정확한 맞춤법과 완성된 문장으로 질문하지 않습니다.

현재 robustness에는 다음 유형을 포함합니다.
```text
오타
띄어쓰기 오류
조사 생략
짧은 키워드
날짜 표현 변형
금액 표현 변형
```
예:
```text
오타
신청 기갼 언제야?

띄어쓰기 오류
신청기간언제야

조사 생략
신청기간 언제

짧은 키워드
신청기간

날짜 표현 변형
8월 31일~9월 2일
8/31~9/2
8.31-9.2

금액 표현 변형
12,000,000원
1200만원
1천2백만원
```
`colloquial`은 자연스러운 구어체 사용성을 보고, `robustness`는 입력이 의도적으로 축소되거나 변형되어도 검색이 유지되는지 확인합니다.


# 8. 평가 Excel 핵심 컬럼

사람이 작성하는 주요 컬럼:
```text
question_id
user_input
reference
reference_text
expected_behavior
category
difficulty
test_group
```
실행 후 자동 저장:
```text
retrieved_chunk_ids
retrieved_contexts
response
run_id
git_commit
```
Metric 실행 후:
```text
recall_at_1
recall_at_3
recall_at_5
faithfulness
response_relevancy
factual_correctness
recall_match_method
recall_matched_rank
recall_match_score
ragas_status
```
필요한 경우 보조 분석:
```text
human_score
failure_type
human_comment
```

# 9. `reference`와 `reference_text`

두 값은 역할이 다릅니다.
```text
reference
→ 모범 답변
→ Generation 평가에 사용

reference_text
→ 정답을 만들 수 있는 원문 근거
→ Retrieval 평가에 사용
```
따라서:
```text
reference 수정
→ Factual Correctness에 영향

reference_text 수정
→ Recall@K에 영향
```

# 10. 현재 주 평가 방식: 임시 평가 DB

현재 평가 DB 이름:
```text
one_cycle_evaluation_tmp
```
운영 DB와 분리하는 이유:
```text
평가 문서가 사용자 서비스 검색 대상에 섞이는 것 방지
평가용 ProcessingRun 누적 영향 방지
Publish 상태 충돌 방지
평가 데이터 삭제 시 운영 데이터 보호
```

# 11. 왜 Fixed File 평가에서 평가 DB 방식으로 바꿨는가

이전 Fixed 평가:
```text
chunks.json
+
embeddings.npy
→ FixedFileRetriever
→ Vector Search
```
현재 실제 서비스 Retrieval:
```text
Vector Search
+
Keyword Search
→ RRF
```
평가가 Vector Search만 사용하면 실제 서비스와 검색 경로가 달라집니다.

따라서 현재 주 평가 경로는:
```text
평가 원본 HWP/HWPX
→ one_cycle_evaluation_tmp
→ 실제 Document Pipeline
→ 실제 Vector Search
→ 실제 Keyword Search
→ RRF
→ 실제 Generation
→ /api/chat
```
입니다.

`fixed_rag/` 코드는 Repository에 남아 있지만 현재 서비스 성능 평가에서는 이전/비교용 경로로 봅니다.


# 12. 평가 DB 생성과 안전장치

평가 DB 생성:
```bash
python backend/scripts/evaluation/create_evaluation_db.py
```
스크립트는 다음을 수행합니다.
```text
평가 DB 생성
→ pgvector 활성화
→ Alembic migration
→ 정상 생성 검증
```
삭제:
```bash
python backend/scripts/evaluation/drop_evaluation_db.py
```
평가 Service에는 `_assert_evaluation_database()` 안전장치가 있습니다.

확인:
```text
settings.postgres_db
+
SELECT current_database()
```
둘 다:
```text
one_cycle_evaluation_tmp
```
인지 확인합니다.

운영 DB 보호를 위해 이 검증은 유지해야 합니다.


# 13. 평가 원본 등록

파일:
```text
backend/app/services/evaluation_service.py
```
핵심 함수:
```text
register_evaluation_dataset()
```
입력 개념:
```text
evaluation_document_id
source_path
document_format
title
```
평가에서는 Crawler를 다시 실행하지 않고 고정 원본 파일을 기존 Crawler Persistence 형식에 맞춰 등록합니다.

처리 흐름:
```text
평가 원본 파일
→ 파일/형식 검증
→ SHA256 계산
→ Collection Payload 구성
→ persist_collection_result()
→ CollectionRun
→ Announcement
→ Document
```
지원 형식:
```text
hwp
hwpx
```

# 14. 실제 Document Pipeline 실행과 Publish

파일:
```text
backend/app/services/evaluation_pipeline_service.py
```
핵심 함수:
```text
process_and_publish_evaluation_collection()
```
흐름:
```text
collection_run_id
→ 평가 DB 검증
→ Document ID 조회
→ process_document_ids()
→ 실제 Document Pipeline
→ 처리 결과 검증
→ publish_collection_run()
```
평가용 Parser/Normalizer/Chunker를 따로 만들지 않고 기존 Pipeline을 그대로 사용합니다.

Publish 전 확인:
```text
active ProcessingRun
active ChunkSet
Chunk 수
완료된 Embedding 수
Embedding model_name
```
문서 하나라도 처리 실패하면 Publish하지 않습니다.


# 15. 실제 Retrieval 구조

현재 Retrieval:
```text
사용자 질문
      ↓
BGE-M3 Query Embedding
      ↓
Vector Search ───────┐
                     ├─→ RRF → Hybrid Top-K
Keyword Search ──────┘
```
Generation에는 최종 Hybrid Search 결과가 전달됩니다.
```text
Hybrid SearchResult
→ Context
→ Prompt
→ Generation LLM
→ Answer
```
세부 구현은:
```text
docs/RAG_RETRIEVAL_GENERATION_HANDOVER.md
```
를 참고합니다.


# 16. `evaluate_rag.py`

파일:
```text
evaluation/evaluate_rag.py
```
역할:
```text
Excel.user_input
→ 실제 POST /api/chat
→ Answer + Evidence
→ 결과 Excel 저장
```
이 연결은 Python import가 아니라 **HTTP API**입니다.

기본 Endpoint:
```text
http://127.0.0.1:8000/api/chat
```
환경변수:
```text
EVAL_API_BASE_URL
EVAL_TIMEOUT_SECONDS
```

# 17. API Request / Response

Request:
```json
{
  "announcementId": 15,
  "question": "신청 기간은 언제인가요?"
}
```
`announcementId`는 평가 DB의 실제 `announcements.id`입니다.

평가 코드가 사용하는 Response:
```text
answer
evidence
```
Evidence 대표 필드:
```text
chunkId
sectionTitle
content
score
```

# 18. 결과 Excel에 저장되는 값

API의:
```text
answer
```
는 Excel:
```text
response
```
에 저장합니다.

Evidence에서는:
```text
retrieved_chunk_ids
retrieved_contexts
```
를 만듭니다.

`retrieved_contexts`는 Rank 순서와 함께 저장되어 이후 Recall과 Faithfulness 평가에 사용됩니다.


# 19. Retrieved Context를 반드시 저장하는 이유

Answer만 보면 실패 원인을 구분하기 어렵습니다.
```text
정답 근거가 검색되지 않음
→ Retrieval 또는 앞단 Pipeline 문제

정답 근거는 검색됨
+ Answer가 틀림
→ Generation / Prompt 문제 가능성
```
따라서 Retrieval 변경을 비교할 때는 반드시:
```text
retrieved_chunk_ids
retrieved_contexts
Recall@K
```
를 함께 봅니다.


# 20. 중간 저장과 Retry

`evaluate_rag.py`는 질문 하나가 끝날 때마다 결과 Excel을 저장합니다.

따라서 긴 평가 중 프로세스가 중단되어도 이미 완료된 문항 결과가 남을 수 있습니다.

Retry 옵션:
```text
--retry
```
요청이 모두 실패하면:
```text
[API ERROR] ...
```
형태로 기록하고 다음 문항으로 진행합니다.


# 21. Retrieval 평가: Recall@K

파일:
```text
evaluation/evaluate_metrics.py
```
현재 계산:
```text
Recall@1
Recall@3
Recall@5
```
의미:
```text
정답에 필요한 원문 근거가
검색 결과 상위 K개 안에서 확인되는가?
```
대표 KPI는 주로:
```text
Recall@3
```
를 사용합니다.


# 22. Recall 계산 방식

현재 Recall은 Gold Chunk ID 방식이 아닙니다.
```text
reference_text
↕
retrieved_contexts
```
를 비교해 Evidence Match를 판정합니다.

이유는 Pipeline을 다시 실행하면 Chunk ID가 바뀔 수 있기 때문입니다.

핵심 함수:
```text
split_retrieved_contexts()
normalize_text()
extract_numbers()
extract_tokens()
number_coverage()
token_coverage()
partial_similarity()
evidence_matches()
recall_at_k()
```
세부 Threshold나 판정 로직을 수정할 때만 실제 `evaluate_metrics.py`를 확인하면 됩니다.


# 23. 복합 질문 Recall

Hard/Condition 질문은 정답 근거가 여러 Chunk에 나뉠 수 있습니다.

현재 `recall_at_k()`는:
```text
개별 Context 검사
→ 실패하면
Top-K Context 통합
→ 다시 Evidence Match
```
를 수행합니다.

따라서 여러 Chunk가 합쳐져야 답할 수 있는 질문도 평가할 수 있습니다.


# 24. Unanswerable의 Recall 처리

현재 코드에서는 `expected_behavior`를 직접 읽어 Recall을 제외하지 않습니다.

`reference_text`가 비어 있으면:
```text
Recall@K = N/A
```
로 처리합니다.

즉 Unanswerable 질문의 Recall 여부는 현재 구현상 `reference_text` 존재 여부와 연결됩니다.


# 25. Generation 평가: RAGAS

현재 주요 자동 Metric:
```text
Faithfulness
Response Relevancy
Factual Correctness
```
---

## 25.1 Faithfulness
```text
생성 답변이 검색 Context에 근거하고 있는가?
```
```text
response
↕
retrieved_contexts
```
---

## 25.2 Response Relevancy
```text
답변이 사용자 질문과 관련 있는가?
```
```text
user_input
↕
response
```
---

## 25.3 Factual Correctness
```text
생성 답변의 사실이 모범답안과 일치하는가?
```
```text
response
↕
reference
```

# 26. Generation LLM과 Judge LLM

둘은 같을 필요가 없습니다.
```text
Generation LLM
→ 사용자 답변 생성

RAGAS Judge
→ 생성 답변 평가
```
Judge는 더 큰 모델을 사용할 수 있습니다.

단, RUN 간 Judge가 달라지면 평가 조건도 달라지므로 반드시 기록해야 합니다.


# 27. RAGAS 연결

OpenAI-compatible Endpoint를 사용합니다.

환경변수:
```text
RAGAS_API_BASE_URL
RAGAS_API_KEY
RAGAS_MODEL
RAGAS_EMBEDDING_MODEL
```
특정 문항만 실행:
```text
--question-ids
```
Factual Correctness만:
```text
--factual-only
```
한국어 Adaptation:
```text
--adapt-factual-korean
```
Recall만 실행:
```text
--skip-ragas
```

# 28. 주요 파일과 역할

| 파일 | 역할 |
| --- | --- |
| `evaluation/evaluate_rag.py` | `/api/chat` 호출 및 Answer/Evidence 저장 |
| `evaluation/evaluate_metrics.py` | Recall@K와 RAGAS 계산 |
| `backend/app/services/evaluation_service.py` | 평가 원본을 평가 DB에 등록 |
| `backend/app/services/evaluation_pipeline_service.py` | 실제 Pipeline 실행 후 Publish |
| `backend/scripts/evaluation/create_evaluation_db.py` | 평가 DB 생성 |
| `backend/scripts/evaluation/drop_evaluation_db.py` | 평가 DB 삭제 |
| `tests/backend/test_evaluation_services.py` | 평가 DB 안전장치/Publish 테스트 |
| `evaluation/evaluate_rag_fixed.py` | 이전 Fixed File 평가 |
| `evaluation/fixed_rag/` | 이전 파일 기반 Retriever |


# 29. 주요 함수

| 기능 | 파일 | 함수 |
| --- | --- | --- |
| Dataset Alias | `evaluate_rag.py` | `normalize_dataset_name()` |
| API 호출 | `evaluate_rag.py` | `http_post_json()` |
| Chunk ID 저장 | `evaluate_rag.py` | `serialize_chunk_ids()` |
| Context 저장 | `evaluate_rag.py` | `serialize_contexts()` |
| 전체 질문 실행 | `evaluate_rag.py` | `evaluate()` |
| Evidence Match | `evaluate_metrics.py` | `evidence_matches()` |
| Recall@K | `evaluate_metrics.py` | `recall_at_k()` |
| RAGAS Scorer | `evaluate_metrics.py` | `build_ragas_scorers()` |
| 전체 Metric | `evaluate_metrics.py` | `evaluate_metrics()` |
| 평가 문서 등록 | `evaluation_service.py` | `register_evaluation_dataset()` |
| 평가 DB 검증 | Evaluation Service | `_assert_evaluation_database()` |
| 문서 처리+Publish | `evaluation_pipeline_service.py` | `process_and_publish_evaluation_collection()` |


# 30. 다른 파트와의 연결 관계

## HTTP
```text
evaluate_rag.py
→ POST /api/chat
```
```text
evaluate_metrics.py
→ RAGAS Judge HTTP API
```
---

## Python import / 함수 호출
```text
evaluation_pipeline_service.py
→ process_document_ids()

evaluation_service.py
→ persist_collection_result()

evaluation_pipeline_service.py
→ publish_collection_run()
```
---

## DB
```text
Backend / Pipeline / Retrieval
→ SQLAlchemy
→ PostgreSQL
→ one_cycle_evaluation_tmp
```
Vector Search:
```text
pgvector
```
---

## 파일
```text
evaluation/datasets/*.xlsx
evaluation/source_documents/**/*.hwp(x)
evaluation/results/*.xlsx
```
Excel 처리:
```text
openpyxl
```

# 31. 실제 한 문항의 데이터 흐름
```text
Excel.user_input
        ↓
announcement_id + question
        ↓ HTTP
POST /api/chat
        ↓
Hybrid Retrieval
        ↓
SearchResult Top-K
        ↓
Generation
        ↓
answer + evidence[]
        ↓
evaluate_rag.py
        ↓
retrieved_chunk_ids
retrieved_contexts
response
        ↓
Result Excel
        ↓
evaluate_metrics.py
       / \
      /   \
reference_text   reference
      ↓             ↓
Retrieved Context   response
      ↓             ↓
Recall@K          RAGAS
```

# 32. 실행환경

서비스/문서처리/RAG:
```bash
source ~/ddokbot/venvs/venv/bin/activate
```
평가 Metric:
```text
eval_venv
```
평가 관련 주요 패키지:
```text
ragas
openai
sentence-transformers
openpyxl
```

# 33. 평가 DB 생성
```bash
python backend/scripts/evaluation/create_evaluation_db.py
```
평가 Backend는 반드시:
```text
POSTGRES_DB=one_cycle_evaluation_tmp
```
를 사용해야 합니다.

환경변수를 바꾼 뒤 이미 떠 있는 Uvicorn이 이전 DB 설정을 유지할 수 있으므로 Backend를 재시작해야 합니다.


# 34. Backend 실행 예시
```bash
python -m uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port 8000
```
실제 FastAPI 객체명과 포트는 현재 실행 환경 기준으로 확인합니다.


# 35. RAG 답변 생성

BD:
```bash
python evaluation/evaluate_rag.py \
  --dataset BD \
  --announcement-id <평가 DB announcement.id>
```
GC:
```bash
python evaluation/evaluate_rag.py \
  --dataset GC \
  --announcement-id <평가 DB announcement.id>
```

# 36. Recall만 계산
```bash
python evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_RUN_001_result.xlsx \
  --output evaluation/results/BD_FINAL_V1_RUN_001_scored.xlsx \
  --skip-ragas
```

# 37. RAGAS 전체 계산
```bash
python evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_RUN_001_result.xlsx \
  --output evaluation/results/BD_FINAL_V1_RUN_001_scored.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "<Judge Model>"
```

# 38. 특정 문항만 재평가
```bash
python evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_RUN_001_scored.xlsx \
  --output evaluation/results/BD_FINAL_V1_RUN_001_scored.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "<Judge Model>" \
  --question-ids Q005 \
  --factual-only \
  --adapt-factual-korean
```

# 39. 자원 부족 시 평가 분리

Generation LLM과 Judge LLM을 같은 GPU에서 동시에 실행하면 자원이 부족할 수 있습니다.

권장:
```text
1단계
Backend + Generation LLM
→ evaluate_rag.py
→ Answer/Evidence 저장

2단계
Generation LLM 종료 또는 자원 확보

3단계
Judge LLM
→ evaluate_metrics.py
→ RAGAS 계산
```
RAG 답변 결과 Excel이 있으면 Metric은 나중에 따로 계산할 수 있습니다.


# 40. RUN 관리

RUN마다 최소한 다음을 기록합니다.
```text
run_id
git_commit
Generation Model
Judge Model
Embedding Model
Retrieval 방식
Top-K
RRF 설정
Dataset Version
Recall 기준 변경 여부
```
한 번에 여러 조건을 바꾸지 않는 것이 중요합니다.


# 41. 결과 분석

전체 평균만 보면 특정 질문 유형의 약점이 숨을 수 있습니다.

권장:
```text
전체 평균
frequent
variant
condition
hard
colloquial
robustness
unanswerable
```
예:
```text
전체 Recall@3   92%
frequent        98%
variant         94%
condition       86%
hard            75%
robustness      82%
```
이렇게 봐야 어떤 입력 유형을 개선해야 하는지 알 수 있습니다.


# 42. Unanswerable 평가

Unanswerable은 일반 질문과 목표가 다릅니다.

일반 질문:
```text
정답 정보 제공
```
Unanswerable:
```text
문서에 없는 정보를 만들지 않음
```
현재 `evaluate_metrics.py`가 `expected_behavior` 기반 Correct Rejection Rate를 자동 계산하는 구조는 아닙니다.

따라서 Unanswerable은 별도로 기대 응답을 확인해야 합니다.


# 43. Human Review

최종 평가는 자동 Metric 중심으로 운영할 수 있습니다.

Human Review는 전체 문항을 다시 수동 채점하기보다 다음 용도로 사용하는 것이 효율적입니다.
```text
자동 Metric 이상치 확인
잘못된 답변의 원인 분석
Judge 판정 오류 확인
```
대표 컬럼:
```text
human_score
failure_type
human_comment
```

# 44. Failure Analysis

오답이 발생했을 때 권장 순서:
```text
1. reference / reference_text 확인
2. 원본 문서 확인
3. Parsed JSON 확인
4. Structured JSON 확인
5. Chunk 확인
6. DB Chunk/Embedding 확인
7. retrieved_contexts 확인
8. response 확인
9. RAGAS Judge 확인
```
Failure Type 예:
```text
Dataset / Reference
Parser
Normalizer
Structure
Chunking
Embedding
Retrieval
Generation / Prompt
DB / API
RAGAS / Judge
복합
```

# 45. 대표 결과 해석

## Recall@3 = 0 / Factual = 0

우선 Retrieval 또는 앞단 데이터 누락을 확인합니다.

---

## Recall@3 = 1 / Factual = 0

근거는 검색했지만 Generation 또는 Judge 판정 문제가 있을 수 있습니다.

확인:
```text
retrieved_contexts
response
reference
```
---

## Recall@1 = 0 / Recall@3 = 1

정답 Chunk는 찾았지만 Rank가 낮습니다.

RRF/Hybrid Search 개선 여부를 볼 때 중요합니다.


# 46. Hybrid Search 적용 후 Answer가 같을 때

Answer가 같다고 Retrieval이 같다고 판단하면 안 됩니다.

먼저 비교:
```text
retrieved_chunk_ids
retrieved_contexts
recall_at_1
recall_at_3
recall_at_5
```
확인:
```text
최신 Backend로 재시작했는가
평가 DB를 바라보는가
평가 Collection이 Publish되었는가
Vector/Keyword 결과가 RRF에 들어가는가
Generation에 Hybrid Top-K가 전달되는가
```

# 47. 주요 트러블슈팅

## API Connection Refused

확인:
```bash
ps -ef | grep uvicorn | grep -v grep
sudo lsof -i :8000
```
환경변수:
```bash
echo $EVAL_API_BASE_URL
```
---

## 평가 DB가 아닌 경우

확인:
```bash
echo $POSTGRES_DB
```
기대:
```text
one_cycle_evaluation_tmp
```
DB:
```sql
SELECT current_database();
```
---

## Publish 실패

확인:
```text
Document role
download_status
ProcessingRun active
ChunkSet active
Chunk 수
Embedding 완료 수
Embedding model_name
```
---

## RAGAS가 너무 오래 걸림

목적에 따라:
```text
--skip-ragas
--factual-only
--question-ids
```
를 사용합니다.

---

## Excel 저장 실패

결과 파일을 Excel이나 다른 Python 프로세스가 사용 중인지 확인합니다.


# 48. 현재 구조의 한계

## Recall

Gold Chunk ID가 아니라 `reference_text` 기반 Heuristic Matching입니다.

장점:
```text
Chunk ID가 재실행 때 바뀌어도 평가 가능
```
한계:
```text
표현 차이로 False Negative 가능
비슷한 숫자/토큰으로 False Positive 가능
```
---

## RAGAS

Judge 모델과 Prompt에 영향을 받습니다.

동일 답변도 Judge가 달라지면 점수가 달라질 수 있습니다.

---

## Fixed RAG 코드가 남아 있음

현재 Repository에는 파일 기반 평가 코드도 남아 있습니다.
```text
evaluate_rag_fixed.py
prepare_fixed_documents.py
fixed_rag/
```
현재 주 평가 방식과 혼동하지 않아야 합니다.


# 49. Docker 분리 전 확인

## localhost

현재 기본:
```text
RAG API
127.0.0.1:8000

Judge API
127.0.0.1:8080/v1
```
컨테이너 분리 시 Service Name 기반 주소로 변경해야 할 수 있습니다.

---

## Python import

현재:
```text
evaluation_pipeline_service
→ integration_service
```
등은 직접 Python 호출입니다.

서비스를 분리하면 HTTP/Queue 연결을 검토해야 합니다.

---

## 평가 원본 파일

평가 Service는 실제 `source_documents` 파일 경로를 읽습니다.

컨테이너가 해당 파일을 볼 수 있도록 Volume Mount가 필요합니다.

---

## DB

Backend / Pipeline / Retrieval 모두 같은:
```text
one_cycle_evaluation_tmp
```
를 바라봐야 합니다.


# 50. 테스트

대표 테스트:
```text
tests/backend/test_evaluation_services.py
```
주요 확인 내용:
```text
운영 DB에서 평가 실행 거부
설정 DB와 실제 DB 불일치 거부
문서처리 실패 시 Publish 거부
성공 시 Publish 수행
Chunk/Embedding 결과 검증
```

# 51. 수정 전 체크리스트

- [ ] 평가 원본 문서가 이전 RUN과 같은가
- [ ] Dataset Version이 같은가
- [ ] 질문/Reference가 변경되지 않았는가
- [ ] 평가 DB를 사용하고 있는가
- [ ] Backend를 최신 코드로 재시작했는가
- [ ] Active Collection이 평가 DB에 Publish되었는가
- [ ] Embedding Model이 동일한가
- [ ] Retrieval 설정이 동일한가
- [ ] Recall 기준이 동일한가
- [ ] Generation Model을 기록했는가
- [ ] Judge Model을 기록했는가
- [ ] 결과 파일을 이전 RUN에 덮어쓰지 않는가


# 52. 평가 후 체크리스트

- [ ] 질문 수가 예상과 같은가
- [ ] `[API ERROR]` 문항이 없는가
- [ ] `response`가 저장되었는가
- [ ] `retrieved_chunk_ids`가 저장되었는가
- [ ] `retrieved_contexts`가 저장되었는가
- [ ] Recall@1/3/5가 계산되었는가
- [ ] `ragas_status`가 정상인가
- [ ] Unanswerable을 별도로 확인했는가
- [ ] Hard/Condition/Robustness를 별도 확인했는가
- [ ] 이전 RUN과 Context Rank를 비교했는가
- [ ] Git Commit / Model / RUN 정보를 기록했는가


# 53. 후임자가 처음 확인할 순서
```text
1. 이 문서
→ 전체 평가 구조 이해

2. docs/BACKEND_DB_EVALUATION_WORKFLOW.md
→ 평가 DB 등록/Publish 세부 구조

3. evaluation_service.py
→ 평가 원본 등록 방식

4. evaluation_pipeline_service.py
→ 실제 Pipeline 재사용

5. RAG_RETRIEVAL_GENERATION_HANDOVER.md
→ Hybrid Retrieval/Generation

6. evaluate_rag.py
→ API 결과 수집

7. evaluate_metrics.py
→ Recall/RAGAS

8. test_evaluation_services.py
→ 안전장치

9. GC 또는 BD 한 세트 실제 실행
```

# 54. 증상별 빠른 확인 위치

| 증상 | 먼저 볼 곳 |
| --- | --- |
| Dataset 인식 실패 | `normalize_dataset_name()` |
| 평가 DB 실행 거부 | `POSTGRES_DB`, `_assert_evaluation_database()` |
| Document 처리 안 됨 | `document_role`, `download_status` |
| Publish 실패 | ProcessingRun / ChunkSet / Embedding |
| API 연결 실패 | Uvicorn / `EVAL_API_BASE_URL` |
| Evidence 없음 | `/api/chat` Response / Retrieval |
| Hybrid 적용 전후 Answer 동일 | `retrieved_chunk_ids`, `retrieved_contexts` |
| Recall 0인데 근거가 보임 | `reference_text`, `evidence_matches()` |
| Recall 1인데 답변 틀림 | Generation / Prompt |
| 답변 맞는데 Factual 0 | Reference / Judge |
| RAGAS 실패 | Judge Endpoint / `ragas_status` |
| Excel 저장 실패 | 파일 Lock / 동시 실행 |


# 55. 현재 코드 기준 주의사항

## Dataset Help 문구

실제 지원 Dataset은:
```text
GC
BD
```
이지만 일부 CLI Help/Error 문자열에 이전 `HC` 표기가 남아 있을 수 있습니다.

실제 지원 여부는:
```text
normalize_dataset_name()
```
기준으로 확인합니다.

---

## Unanswerable

현재 Recall은:
```text
expected_behavior
```
가 아니라:
```text
reference_text 존재 여부
```
를 기준으로 N/A를 결정합니다.

---

## 현재 주 평가 경로

Repository에 `fixed_rag/`가 있어도 현재 서비스 성능 평가의 주 경로는:
```text
Evaluation DB
→ 실제 Pipeline
→ 실제 Hybrid Retrieval
→ 실제 Generation
```
입니다.


# 56. 최종 요약

현재 DDOKBOT Evaluation의 핵심 구조:
```text
고정 평가 HWP/HWPX
+
고정 평가 Excel
        ↓
one_cycle_evaluation_tmp
        ↓
실제 Document Pipeline
        ↓
Chunk + BGE-M3 Embedding
        ↓
Publish
        ↓
Vector Search + Keyword Search
        ↓
RRF
        ↓
Generation
        ↓
/api/chat
        ↓
evaluate_rag.py
        ↓
response
retrieved_chunk_ids
retrieved_contexts
        ↓
evaluate_metrics.py
        ↓
Recall@1 / @3 / @5
Faithfulness
Response Relevancy
Factual Correctness
        ↓
RUN 비교
Failure Analysis
```
후임자가 가장 중요하게 기억해야 할 원칙은 다음과 같습니다.

1. **현재 주 평가 경로는 임시 평가 DB 기반 실제 서비스 경로입니다.**
2. **Retrieval 변경을 볼 때 Answer만 보지 말고 Retrieved Chunk/Context를 같이 비교합니다.**
3. **Recall은 Gold Chunk ID가 아니라 `reference_text` 기반 Heuristic Match입니다.**
4. **RUN 비교 시 Dataset, Retrieval 설정, Generation Model, Judge Model, Recall 기준을 함께 고정하고 기록합니다.**

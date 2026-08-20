# DDOKBOT Evaluation

> 이 문서는 DDOKBOT의 RAG 평가 구조와 실행 방법을 설명합니다.
>
> 새로운 개발자 또는 AI가 이 문서만 읽고도 다음 내용을 이해할 수 있도록 작성되었습니다.
>
> - 평가셋이 어디에 있는지
> - 평가 대상 문서가 무엇인지
> - `evaluate_rag.py`와 `evaluate_metrics.py`의 역할이 어떻게 나뉘는지
> - 질문을 `/api/chat`에 자동 전송하는 방법
> - Retrieval과 Generation 품질을 어떤 지표로 평가하는지
> - RAGAS를 어떻게 실행하는지
> - RUN_001, RUN_002처럼 반복 실험을 어떻게 관리하는지
> - 사람이 직접 검수해야 하는 항목은 무엇인지
> - 낮은 점수가 나왔을 때 어느 Pipeline Stage부터 확인해야 하는지

---

# 1. Evaluation 목적

DDOKBOT Evaluation은 동일한 평가 질문을 기준으로 RAG의 검색 품질과 최종 답변 품질을 반복 측정하기 위한 영역입니다.

평가 흐름:

```text
Evaluation Dataset
      ↓
evaluate_rag.py
      ↓
POST /api/chat
      ↓
Retrieved Context + Answer 저장
      ↓
evaluate_metrics.py
      ↓
Recall@K + RAGAS
      ↓
Human Review
      ↓
Failure Analysis
      ↓
Code Improvement
      ↓
Next RUN
```

평가의 핵심 원칙:

```text
같은 평가셋
    +
같은 문서
    +
다른 코드 버전
    ↓
RUN별 성능 비교
```

코드 개선 효과를 확인하려면 평가 질문과 정답 기준을 RUN마다 바꾸지 않습니다.

---

# 2. Evaluation Root

평가 관련 파일 위치:

```text
evaluation/
```

현재 권장 구조:

```text
evaluation/
├── evaluate_rag.py
├── evaluate_metrics.py
│
├── datasets/
│   ├── GC_FINAL_V1.xlsx
│   └── HC_FINAL_V1.xlsx
│
├── source_documents/
│   ├── DOC_GC_001/
│   │   └── v1/
│   └── DOC_HC_001/
│       └── v1/
│
└── results/
    └── .gitkeep
```

`results/`는 평가 실행 시 자동 생성되는 결과 파일을 저장합니다.

---

# 3. 현재 평가 대상 문서

현재 기본 평가 문서는 두 개입니다.

```text
GC
→ 고창율계 고령자복지주택(영구임대)

HC
→ 화천신읍2 영구임대(화천용신마을)
```

Dataset Code:

| 코드 | 문서 |
|---|---|
| `GC` | 고창율계 고령자복지주택 |
| `HC` | 화천신읍2 영구임대 |

평가셋 파일:

```text
evaluation/datasets/GC_FINAL_V1.xlsx
evaluation/datasets/HC_FINAL_V1.xlsx
```

---

# 4. 평가셋 구성 원칙

현재 평가셋은 문서당 60개 질문을 기준으로 구성합니다.

질문 그룹:

```text
frequent
variant
condition
hard
colloquial
unanswerable
```

권장 구성:

| test_group | 개수 | 목적 |
|---|---:|---|
| `frequent` | 25 | 실제 사용자가 자주 물을 질문 |
| `variant` | 12 | 같은 의미의 다양한 표현 |
| `condition` | 7 | 조건형/부정형 질문 |
| `hard` | 8 | 비교·복합 정보·추론형 질문 |
| `colloquial` | 3 | 짧은 말투·구어체·키워드형 질문 |
| `unanswerable` | 5 | 문서에 없는 질문의 거절 여부 확인 |

총:

```text
60 questions / document
```

두 문서를 모두 평가하면:

```text
120 evaluation cases
```

입니다.

---

# 5. 평가셋 Excel

현재 주요 Sheet:

```text
평가셋
평가설계
실행기록
사용가이드
```

자동 평가 Script는 기본적으로:

```text
평가셋
```

Sheet를 읽습니다.

다른 Sheet는 평가 설계와 실행 이력을 사람이 확인하기 위한 보조 영역입니다.

---

# 6. 평가셋 주요 Column

현재 주요 Column:

```text
document_id
question_id
test_group
intent_id
category
difficulty
style
expression_type
variant_group

user_input
reference
reference_source
reference_text
expected_behavior

retrieved_chunk_ids
retrieved_contexts
response

recall_at_1
recall_at_3
recall_at_5

context_precision
context_recall
faithfulness
response_relevancy
factual_correctness

human_score
failure_type
human_comment

run_id
git_commit
source_file
```

---

# 7. Column 역할

질문:

```text
user_input
```

정답 기준:

```text
reference
reference_text
```

실제 RAG 검색 결과:

```text
retrieved_chunk_ids
retrieved_contexts
```

실제 답변:

```text
response
```

자동 평가:

```text
recall_at_1
recall_at_3
recall_at_5

context_precision
context_recall
faithfulness
response_relevancy
factual_correctness
```

사람 검수:

```text
human_score
failure_type
human_comment
```

실험 추적:

```text
run_id
git_commit
```

---

# 8. expected_behavior

문항별 기대 동작:

```text
answer
refuse
```

개념:

```text
answer
→ 문서 근거를 기반으로 답변해야 함

refuse
→ 문서에 없는 정보이므로 추측하지 않고
   확인할 수 없다고 안내해야 함
```

`unanswerable` 문항은 주로:

```text
expected_behavior = refuse
```

형태로 관리합니다.

---

# 9. evaluate_rag.py

파일:

```text
evaluation/evaluate_rag.py
```

역할:

```text
Excel 질문 읽기
      ↓
POST /api/chat
      ↓
RAG Response 수집
      ↓
Evidence 저장
      ↓
Answer 저장
      ↓
run_id / git_commit 기록
      ↓
Result Excel 저장
```

이 Script는 평가 점수를 계산하는 파일이 아닙니다.

주 목적은:

```text
RAG 실행 결과 수집
```

입니다.

---

# 10. evaluate_rag.py 입력

기본 Dataset:

```text
GC
```

입력 파일:

```text
evaluation/datasets/GC_FINAL_V1.xlsx
```

또는:

```text
evaluation/datasets/HC_FINAL_V1.xlsx
```

API:

```text
POST /api/chat
```

Request:

```json
{
  "announcementId": 15,
  "question": "인터넷 신청 기간은 언제인가요?"
}
```

---

# 11. evaluate_rag.py가 기대하는 API Response

기본 형태:

```json
{
  "answer": "...",
  "grounded": true,
  "evidence": [
    {
      "chunkId": 123,
      "sectionTitle": "...",
      "content": "...",
      "score": 0.82
    }
  ]
}
```

평가 Script는 이 중:

```text
answer
evidence
```

를 Excel에 기록합니다.

---

# 12. Evidence 저장 형식

`retrieved_chunk_ids`:

```text
123, 456, 789
```

`retrieved_contexts`:

```text
[rank=1 | chunkId=123 | section=... | score=...]
Context Text

---

[rank=2 | chunkId=456 | section=... | score=...]
Context Text
```

형태로 저장합니다.

이 값은 이후 Retrieval 평가와 실패 원인 분석에 사용합니다.

---

# 13. RUN 관리

코드 수정 전후 성능 비교를 위해 RUN 번호를 사용합니다.

예:

```text
GC_RUN_001
GC_RUN_002
GC_RUN_003
```

화천:

```text
HC_RUN_001
HC_RUN_002
HC_RUN_003
```

현재 Script에서는 상단의:

```python
DEFAULT_RUN_NUMBER = "001"
```

값을 사용합니다.

첫 평가:

```python
DEFAULT_RUN_NUMBER = "001"
```

코드 수정 후 두 번째 평가:

```python
DEFAULT_RUN_NUMBER = "002"
```

세 번째 평가:

```python
DEFAULT_RUN_NUMBER = "003"
```

---

# 14. RUN별 결과 파일

GC RUN_001:

```text
evaluation/results/
└── GC_FINAL_V1_RUN_001_result.xlsx
```

Metrics까지 실행:

```text
evaluation/results/
├── GC_FINAL_V1_RUN_001_result.xlsx
└── GC_FINAL_V1_RUN_001_scored.xlsx
```

RUN_002:

```text
GC_FINAL_V1_RUN_002_result.xlsx
GC_FINAL_V1_RUN_002_scored.xlsx
```

이전 RUN 결과를 덮어쓰지 않습니다.

---

# 15. evaluate_rag.py 실행

프로젝트 Root:

```bash
cd /home/ubuntu/ddokbot/one-cycle
```

고창:

```bash
python evaluation/evaluate_rag.py \
  --dataset GC \
  --announcement-id 15
```

화천:

```bash
python evaluation/evaluate_rag.py \
  --dataset HC \
  --announcement-id <ANNOUNCEMENT_ID>
```

`announcement-id`는 실제 DB에 저장된 공고 ID를 사용합니다.

---

# 16. 평가 전 Backend 확인

`evaluate_rag.py`는 `/api/chat`을 호출하므로 Backend가 먼저 실행되어 있어야 합니다.

Health:

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

Chat 직접 확인:

```bash
curl -i \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{"announcementId":15,"question":"신청 기간은 언제인가?"}'
```

직접 Chat 호출이 실패하면 평가 Script부터 수정하지 않습니다.

먼저 Backend/RAG 연결을 확인합니다.

---

# 17. evaluate_rag.py 실패 유형

## API Connection Error

예:

```text
API 서버 연결 실패
```

확인:

```text
FastAPI 실행 여부
Port 8000
/api/chat
EVAL_API_BASE_URL
```

---

## HTTP 422

확인:

```text
announcementId
question
ChatRequest Schema
```

---

## HTTP 500

확인:

```text
Backend Traceback
RAG Retrieval
Generation
DB
```

평가 Script 문제가 아닐 수 있습니다.

---

# 18. evaluate_metrics.py

파일:

```text
evaluation/evaluate_metrics.py
```

역할:

```text
evaluate_rag.py Result 읽기
      ↓
Recall@K 계산
      ↓
RAGAS 평가
      ↓
Metric Column 기록
      ↓
Scored Excel 저장
```

입력:

```text
*_result.xlsx
```

출력:

```text
*_scored.xlsx
```

---

# 19. Retrieval 평가

현재 기본 Retrieval Metric:

```text
Recall@1
Recall@3
Recall@5
```

의미:

```text
Recall@1
→ 첫 번째 검색 결과 안에 정답 근거가 있는가

Recall@3
→ 상위 3개 검색 결과 안에 정답 근거가 있는가

Recall@5
→ 상위 5개 검색 결과 안에 정답 근거가 있는가
```

---

# 20. 현재 Recall 계산 방식

현재 Script는 고정된 Gold Chunk ID가 아니라:

```text
reference_text
        ↕
retrieved_contexts
```

를 자동 비교합니다.

기본 Threshold:

```text
0.75
```

개념:

```text
reference_text와 Context의
토큰 일치 + 문자열 유사도
        ↓
Threshold 이상
        ↓
해당 Top-K에서 Hit
```

따라서 현재 Recall은:

```text
Heuristic Recall
```

성격을 가집니다.

엄밀한 Gold Chunk 기반 Recall과는 다릅니다.

---

# 21. Recall Threshold

기본:

```text
0.75
```

실행 시 변경 가능:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --recall-threshold 0.8 \
  --skip-ragas
```

Threshold를 RUN마다 임의로 바꾸면 비교 기준이 달라지므로,
성능 비교 실험에서는 가능한 한 동일한 값을 유지합니다.

---

# 22. Recall만 먼저 실행

RAGAS 없이 Retrieval 결과만 빠르게 확인:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --skip-ragas
```

이 방식은:

```text
Recall@1
Recall@3
Recall@5
```

만 먼저 확인하고 싶을 때 사용합니다.

---

# 23. RAGAS

현재 자동 평가에 사용하는 주요 RAGAS Metric:

```text
Context Precision
Context Recall
Faithfulness
Response Relevancy
Factual Correctness
```

---

# 24. RAGAS Metric 의미

## Context Precision

검색된 Context 중 실제 질문과 정답에 유용한 근거가 얼마나 앞쪽에 잘 배치되었는지 평가합니다.

---

## Context Recall

정답을 구성하는 데 필요한 근거가 검색 Context에 충분히 포함되었는지 평가합니다.

---

## Faithfulness

최종 답변이 검색된 Context를 벗어나 임의로 내용을 생성하지 않았는지 평가합니다.

Hallucination 확인에 중요한 지표입니다.

---

## Response Relevancy

최종 답변이 사용자 질문에 얼마나 직접적으로 관련되어 있는지 평가합니다.

---

## Factual Correctness

생성 답변이 Reference Answer와 사실적으로 얼마나 일치하는지 평가합니다.

---

# 25. RAGAS 실행

예:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --ragas-model <MODEL_NAME>
```

RAGAS LLM 기본 Base URL:

```text
http://127.0.0.1:8080/v1
```

환경변수:

```text
RAGAS_API_BASE_URL
RAGAS_API_KEY
RAGAS_MODEL
RAGAS_EMBEDDING_MODEL
```

---

# 26. Evaluation Dependencies

평가 Script에서 사용하는 주요 Package:

```text
openpyxl
ragas
openai
sentence-transformers
```

RAGAS 없이 Recall만 실행해도:

```text
openpyxl
```

은 필요합니다.

RAGAS 평가를 사용할 경우:

```text
ragas
openai
sentence-transformers
```

가 추가로 필요합니다.

설치 여부 확인:

```bash
python -m pip show \
ragas \
openai \
sentence-transformers \
openpyxl
```

---

# 27. RAGAS Package 오류

예:

```text
Import "ragas" could not be resolved
```

가능성:

```text
현재 Python 환경에 ragas 미설치
VS Code Interpreter 불일치
```

확인:

```bash
which python
python -m pip show ragas
```

VS Code에서는 실제 프로젝트 Python Interpreter를 선택합니다.

---

# 28. Human Review

자동 Metric만으로 최종 품질을 판단하지 않습니다.

현재 사람이 직접 입력하는 주요 Column:

```text
human_score
failure_type
human_comment
```

---

# 29. human_score

권장 기준:

```text
2
→ 정답

1
→ 부분 정답

0
→ 오답
```

예:

```text
Reference
→ 8월 24일~25일, 10:00~16:00

Response
→ 8월 24일~25일
```

날짜는 맞지만 시간이 빠졌다면:

```text
human_score = 1
```

로 볼 수 있습니다.

---

# 30. human_comment

`human_comment`에는 점수만으로 알 수 없는 구체적인 이유를 기록합니다.

예:

```text
날짜는 맞지만 접수시간 10:00~16:00이 누락됨
```

또는:

```text
검색 Context에는 정답 근거가 있었으나
LLM이 최종 답변에 포함하지 않음
```

일반적으로:

```text
human_score = 1 또는 0
```

인 경우 작성하는 것을 권장합니다.

---

# 31. failure_type

대표적인 실패 유형:

```text
Parser
Normalizer
Structure
Chunking
Retrieval
LLM/Prompt
DB/API
복합 원인
```

평가 결과가 낮다고 해서 바로 LLM 문제로 판단하지 않습니다.

---

# 32. Failure Analysis 순서

질문 하나가 실패했을 때 다음 순서로 확인합니다.

```text
Response
   ↓
Retrieved Context
   ↓
DB Chunk
   ↓
Chunk Output
   ↓
Structured Output
   ↓
Normalized Output
   ↓
Parsed Output
   ↓
Original Document
```

핵심 질문:

```text
정답 정보가 마지막으로 정상적으로 존재했던 Stage는 어디인가?
```

그 다음 Stage를 실패 원인 후보로 봅니다.

---

# 33. LLM/Prompt 실패

조건:

```text
retrieved_contexts에 정확한 근거 존재
        +
response가 틀리거나 핵심 정보 누락
```

판단:

```text
failure_type = LLM/Prompt
```

예:

```text
Context
→ 날짜 + 시간 모두 존재

Response
→ 날짜만 답변
```

---

# 34. Retrieval 실패

조건:

```text
DB에는 정답 Chunk가 존재
        +
Top-K 검색 결과에 포함되지 않음
```

판단:

```text
failure_type = Retrieval
```

확인:

```text
query embedding
vector similarity
Top-K
search text
embedding model
```

---

# 35. Chunking 실패

조건:

```text
Structured Output에는 정답 정보 존재
        +
Chunk에서 정보가 잘리거나 관계가 깨짐
```

판단:

```text
failure_type = Chunking
```

예:

```text
표 Header와 Value가 서로 다른 Chunk로 분리되어
의미를 복원할 수 없음
```

---

# 36. Structure 실패

조건:

```text
Parsed/Normalized 결과에는 정보가 정상
        +
Structured 결과에서 제목/표/관계가 잘못됨
```

판단:

```text
failure_type = Structure
```

---

# 37. Parser 실패

조건:

```text
원문에는 정보가 존재
        +
Parsed JSON부터 정보가 누락/손상
```

판단:

```text
failure_type = Parser
```

Parser 문제가 확실하면 뒤의 Chunking/Retrieval부터 수정하지 않습니다.

---

# 38. DB/API 실패

예:

```text
정상 Chunk가 생성되었지만 DB 저장 누락

다른 announcementId 데이터가 검색됨

API Response 변환 과정에서 Evidence 누락
```

판단:

```text
failure_type = DB/API
```

---

# 39. Unanswerable 평가

문서에 없는 질문은 일반 Answerable 질문과 동일하게 평가하지 않습니다.

예:

```text
반려동물 키워도 되나요?
주차비는 얼마인가요?
관리비는 얼마인가요?
가장 가까운 지하철역은 어디인가요?
몇 층에 배정되나요?
```

문서에 근거가 없다면 RAG는 추측하지 않아야 합니다.

권장 동작:

```text
문서에서 확인할 수 없습니다.
```

---

# 40. Correct Rejection

Unanswerable 질문에서는 별도로 다음을 확인할 수 있습니다.

```text
Correct Rejection Rate
```

개념:

```text
정상 거절한 Unanswerable 질문 수
---------------------------------
전체 Unanswerable 질문 수
```

예:

```text
5개 중 4개 정상 거절
→ Correct Rejection Rate = 80%
```

이 지표는 Hallucination 방지 성능을 설명할 때 유용합니다.

현재 자동 Script에 집계가 없으면 Human Review 또는 별도 집계로 확인할 수 있습니다.

---

# 41. 평가 실행 전체 순서

## 1. Backend / RAG 실행 확인

```text
/api/health
/api/chat
```

---

## 2. RUN 번호 확인

두 Script의:

```python
DEFAULT_RUN_NUMBER = "001"
```

값을 확인합니다.

---

## 3. RAG 결과 수집

```bash
python evaluation/evaluate_rag.py \
  --dataset GC \
  --announcement-id 15
```

---

## 4. Retrieval Metric 확인

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --skip-ragas
```

---

## 5. RAGAS 실행

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --ragas-model <MODEL_NAME>
```

---

## 6. Human Review

```text
human_score
failure_type
human_comment
```

입력.

---

## 7. 실패 원인 분석

```text
LLM/Prompt
Retrieval
Chunking
Structure
Parser
DB/API
```

분류.

---

## 8. 코드 수정

문제가 발생한 Stage만 우선 수정.

---

## 9. 다음 RUN

```python
DEFAULT_RUN_NUMBER = "002"
```

로 변경.

동일 평가셋으로 다시 평가합니다.

---

# 42. RUN 비교

예:

```text
GC_RUN_001
→ 개선 전

GC_RUN_002
→ Retrieval 수정 후

GC_RUN_003
→ Prompt 수정 후
```

비교 항목:

```text
Recall@1
Recall@3
Recall@5

Context Precision
Context Recall
Faithfulness
Response Relevancy
Factual Correctness

Human Score
Correct Rejection Rate
```

---

# 43. 평가셋 버전과 RUN의 차이

평가 질문 자체가 같으면:

```text
GC_FINAL_V1.xlsx
```

를 계속 사용합니다.

코드만 바뀌었을 때:

```text
RUN_001
RUN_002
RUN_003
```

을 증가시킵니다.

평가 질문/Reference 자체를 변경했을 때만:

```text
GC_FINAL_V2.xlsx
```

처럼 Dataset Version을 올립니다.

즉:

```text
V1 / V2
→ 평가셋 버전

RUN_001 / RUN_002
→ 코드 실험 버전
```

입니다.

---

# 44. Git Commit 기록

`evaluate_rag.py`는 현재 Git 정보를 확인하여:

```text
git_commit
```

을 각 평가 행에 기록합니다.

목적:

```text
이 평가 결과가
어떤 코드 상태에서 생성되었는지
추적
```

RUN 비교에서 매우 중요합니다.

가능하면 평가 직전에 변경사항을 Commit한 상태에서 실행합니다.

---

# 45. 결과 파일 Git 관리

평가 결과는 실행할 때마다 생성되기 때문에 기본적으로 Git에서 제외하는 것을 권장합니다.

`.gitignore` 예:

```gitignore
# Evaluation results
evaluation/results/*
!evaluation/results/.gitkeep
```

평가셋 자체:

```text
evaluation/datasets/
```

은 Source of Truth 역할을 하므로 Git으로 관리할 수 있습니다.

---

# 46. source_documents 목적

위치:

```text
evaluation/source_documents/
```

평가 Reference를 만든 원본 문서를 보존하기 위한 영역입니다.

예:

```text
evaluation/source_documents/
└── DOC_GC_001/
    └── v1/
        └── source.hwpx
```

목적:

```text
LH 원본이 변경/삭제되더라도
평가 기준 문서를 다시 확인 가능
```

평가 Script가 이 파일을 직접 Parsing하는 것은 아닙니다.

실제 평가는 DB에 등록된:

```text
announcementId
```

를 기준으로 `/api/chat`을 호출합니다.

---

# 47. 평가 결과가 이상할 때

## 모든 질문이 API ERROR

확인:

```text
Backend
/api/chat
announcementId
Port
```

---

## Evidence가 모두 없음

확인:

```text
DB Active Processing Run
ChunkSet
Embeddings
Retrieval
announcement filtering
```

---

## Recall이 낮음

확인:

```text
reference_text
retrieved_contexts
Chunk 품질
Embedding
Top-K
```

---

## Recall은 높은데 답변 점수가 낮음

가능성:

```text
LLM/Prompt
Context Builder
Generation
```

---

## Faithfulness가 낮음

가능성:

```text
Hallucination
Prompt 제약 부족
Context 외 정보 생성
```

---

## Factual Correctness가 낮음

확인:

```text
Reference
Response
숫자/날짜/금액 누락
조건 누락
```

---

# 48. 평가 데이터 수정 주의

첫 공식 RUN 이후에는 비교 실험 중 평가 질문을 임의로 변경하지 않습니다.

잘못된 Reference를 발견한 경우에는:

```text
왜 수정했는지 기록
Dataset Version 증가 여부 검토
```

가 필요합니다.

평가셋과 코드를 동시에 바꾸면:

```text
성능 변화가 코드 때문인지
질문 변화 때문인지
```

구분하기 어렵습니다.

---

# 49. 평가 확장 방향

현재:

```text
2 documents × 60 questions
```

을 기본으로 사용합니다.

이후 일반화 성능을 검증할 때는 질문 수를 무한히 늘리기보다:

```text
임대주택 문서 수 증가
```

를 우선 고려합니다.

예:

```text
4~5 rental-housing notices
×
약 60 cases
```

형태로 확장할 수 있습니다.

단 문서에 존재하지 않는 내용을 억지로 질문으로 만들지 않습니다.

---

# 50. 중간발표용 평가 설명

발표에서는 다음 흐름으로 설명할 수 있습니다.

```text
1. 실제 사용자가 자주 물을 질문을 중심으로 평가셋 구성
2. 같은 의미의 표현 변형 포함
3. 조건형/비교형/구어체 포함
4. 문서에 없는 질문도 포함
5. Retrieval과 Answer Generation을 분리 평가
6. 동일 평가셋으로 코드 수정 전후 성능 비교
```

핵심:

```text
평가셋을 바꾸지 않고
같은 질문으로 반복 측정
```

입니다.

---

# 51. Evaluation Source of Truth

| 영역 | Source of Truth |
|---|---|
| 평가 질문/Reference | `evaluation/datasets/*.xlsx` |
| RAG 실행 수집 | `evaluation/evaluate_rag.py` |
| Recall/RAGAS | `evaluation/evaluate_metrics.py` |
| 평가 원본 문서 | `evaluation/source_documents/` |
| 실행 결과 | `evaluation/results/` |
| Chat API Contract | `backend/app/api/routes/chat.py`, `backend/app/schemas/chat.py` |
| Runtime RAG | `rag/` |
| Chunk/Pipeline | `pipeline/` |
| DB Persistence | `backend/app/services/pipeline_persistence.py` |

---

# 52. AI에게 Evaluation 작업을 맡길 때

최소 전달:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/RAG.md
docs/PIPELINE.md

evaluation/
```

Retrieval 문제까지 포함하면 추가:

```text
rag/
pipeline/chunking/
pipeline/embedding/
backend/app/services/pipeline_persistence.py
```

Generation 문제면 추가:

```text
rag/generation/
rag/service.py
backend/app/services/chat_service.py
```

---

# 53. AI가 Evaluation 수정 전 확인할 질문

```text
1. 평가셋을 바꾸는가, 평가 코드만 바꾸는가?
2. Dataset Version을 올려야 하는가?
3. RUN 번호만 올리면 되는가?
4. Retrieval Metric 문제인가?
5. Generation Metric 문제인가?
6. Unanswerable 질문을 어떻게 처리하는가?
7. 기존 RUN 결과를 덮어쓰지 않는가?
8. 같은 기준으로 전후 비교가 가능한가?
```

평가 기준을 확인하지 않고 Dataset과 Script를 동시에 대폭 변경하지 않습니다.

---

# 54. 전체 Evaluation 연결 구조

```text
GC_FINAL_V1.xlsx / HC_FINAL_V1.xlsx
              │
              ▼
       evaluate_rag.py
              │
              ▼
        POST /api/chat
              │
              ▼
         Backend / RAG
              │
              ▼
       Retrieval + Answer
              │
              ▼
 *_RUN_XXX_result.xlsx
              │
              ▼
     evaluate_metrics.py
              │
        ┌─────┴─────┐
        ▼           ▼
    Recall@K      RAGAS
        │           │
        └─────┬─────┘
              ▼
 *_RUN_XXX_scored.xlsx
              │
              ▼
        Human Review
              │
              ▼
       Failure Analysis
              │
              ▼
       Code Improvement
              │
              ▼
         Next RUN
```

---

# 55. 핵심 요약

DDOKBOT Evaluation의 중심 원칙:

```text
Dataset
→ 질문/정답 기준

evaluate_rag.py
→ 실제 RAG 실행 결과 수집

evaluate_metrics.py
→ Retrieval + Generation 자동 평가

Human Review
→ 자동 평가가 놓친 품질 확인

RUN
→ 코드 수정 전후 비교
```

평가 결과가 낮을 때는 단순히 LLM 성능 문제라고 판단하지 않고:

```text
Parser
→ Normalizer
→ Structure
→ Chunking
→ Embedding
→ Retrieval
→ LLM/Prompt
```

전체 흐름에서 **정답 정보가 마지막으로 정상적으로 존재했던 Stage**를 찾아 실패 원인을 분류합니다.

가장 중요한 원칙:

```text
동일한 평가셋을 유지한 상태에서
RUN만 증가시키며 코드 개선 전후를 비교합니다.
```

# DDOKBOT Evaluation

> 이 문서는 DDOKBOT의 RAG 평가 구조와 실행 방법을 설명합니다.
>
> 주요 내용:
>
> * 평가셋 위치와 구성
> * `evaluate_rag.py`와 `evaluate_metrics.py`의 역할
> * Retrieval / Generation 평가 지표
> * RAGAS 실행 방법
> * RUN 관리 방법
> * Human Review와 실패 원인 분석 방법

---

# 1. Evaluation 목적

DDOKBOT Evaluation은 동일한 평가셋을 기준으로 RAG 시스템의 검색 성능과 답변 품질을 반복 측정하기 위한 영역입니다.

전체 흐름:

```text
Evaluation Dataset
      ↓
evaluate_rag.py
      ↓
POST /api/chat
      ↓
Retrieved Context + Response 저장
      ↓
evaluate_metrics.py
      ↓
Recall@K + RAGAS
      ↓
Automatic Metric Result
      ↓
Human Review
      ↓
Failure Analysis
      ↓
Code Improvement
      ↓
Next RUN
```

최종 정량 성능은 **자동 Metric을 기준으로 판단**합니다.

Human Review는 최종 점수를 대신하는 평가가 아니라, 점수가 낮거나 이상한 문항에서 **어느 부분의 정확성이 떨어졌는지 분석하기 위한 보조 수단**으로 사용합니다.

핵심 원칙:

```text
같은 평가셋
+
같은 평가 대상 문서
+
다른 코드 버전
↓
RUN별 성능 비교
```

한 번 고정한 평가셋은 코드 개선 전후를 비교하는 동안 유지합니다.

---

# 2. Evaluation 구조

```text
evaluation/
├── evaluate_rag.py
├── evaluate_metrics.py
│
├── datasets/
│   ├── GC_FINAL_V1.xlsx
│   └── BD_FINAL_V1.xlsx
│
├── source_documents/
│   ├── DOC_GC_001/
│   └── DOC_BD_001/
│
└── results/
    └── .gitkeep
```

역할:

| 위치                    | 역할                   |
| --------------------- | -------------------- |
| `datasets/`           | 평가 질문과 Reference 저장  |
| `evaluate_rag.py`     | 실제 RAG 실행 결과 수집      |
| `evaluate_metrics.py` | Recall / RAGAS 자동 평가 |
| `source_documents/`   | 평가 기준이 된 원본 문서 보관    |
| `results/`            | RUN별 평가 결과 저장        |

---

# 3. 현재 평가 Dataset

현재 주요 고정 평가 문서:

| Dataset Code | 문서           |
| ------------ | ------------ |
| `GC`         | 고창율계 고령자복지주택 |
| `BD`         | 서울 번동3 행복주택  |

평가셋:

```text
evaluation/datasets/GC_FINAL_V1.xlsx
evaluation/datasets/BD_FINAL_V1.xlsx
```

Dataset Alias 예:

```text
GC / GOCHANG / 고창

BD / BUNDONG / 서울번동
```

---

# 4. 평가셋 구성 원칙

평가셋은 문서별 약 60문항을 기준으로 구성합니다.

단, **모든 문서가 동일한 유형과 동일한 문항 수를 가져야 하는 것은 아닙니다.**

문서마다 정보의 구조와 난이도가 다르기 때문에 평가 목적에 따라 문항 구성을 조정할 수 있습니다.

주요 평가 유형:

| 유형             | 목적                   |
| -------------- | -------------------- |
| `easy`         | 단일 사실 검색 및 답변        |
| `medium`       | 자격·조건·일정 등의 해석       |
| `hard`         | 비교·복합 정보·다중 근거       |
| `robustness`   | 실제 사용자 입력 변형에 대한 견고성 |
| `unanswerable` | 문서에 없는 질문의 잘못된 답변 차단 |

예를 들어 고창은:

```text
easy
medium
hard
unanswerable
```

위주로 구성할 수 있고,

서울 번동은:

```text
easy
medium
hard
robustness
unanswerable
```

형태로 구성할 수 있습니다.

즉, **문서별 구성은 달라도 되지만 동일 문서의 RUN 간 평가셋은 유지합니다.**

---

# 5. Robustness 평가

서울 번동 평가셋에는 실제 사용자 입력 변형을 확인하기 위한 `robustness` 문항을 추가합니다.

주요 유형:

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
정상
→ 신청 기간은 언제인가요?

조사 생략
→ 신청 기간 언제?

짧은 키워드
→ 신청기간

날짜 표현 변형
→ 8/31부터 신청이야?

금액 표현 변형
→ 보증금 2천만원이야?
```

Robustness 평가는 문법적으로 완성된 질문뿐 아니라 실제 사용자가 입력할 수 있는 다양한 표현에서도 검색과 답변이 정상적으로 이루어지는지 확인합니다.

---

# 6. 평가셋 주요 Column

주요 Column:

```text
document_id
question_id
category
difficulty
test_group

user_input
reference
reference_text
expected_behavior

retrieved_chunk_ids
retrieved_contexts
response

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

human_score
failure_type
human_comment

run_id
git_commit
```

역할:

| Column                | 의미                  |
| --------------------- | ------------------- |
| `user_input`          | 실제 질문               |
| `reference`           | 모범 답안               |
| `reference_text`      | 검색되어야 하는 원문 근거      |
| `retrieved_contexts`  | 실제 검색 Context       |
| `response`            | 실제 챗봇 답변            |
| `recall_at_1/3/5`     | Retrieval 평가        |
| `faithfulness`        | 근거 기반 답변 여부         |
| `response_relevancy`  | 질문 관련성              |
| `factual_correctness` | Reference와 사실 일치 여부 |
| `human_score`         | 오류 분석용 수기 점수        |
| `failure_type`        | 실패 Stage            |
| `run_id`              | 실험 버전               |

과거 파일의:

```text
context_precision
context_recall
```

Column은 현재 핵심 평가 Metric으로 사용하지 않습니다.

---

# 7. expected_behavior

문항별 기대 동작:

```text
answer
refuse
```

의미:

```text
answer
→ 문서 근거를 기반으로 답변

refuse
→ 문서에 근거가 없으면 추측하지 않고
   확인할 수 없다고 안내
```

`unanswerable` 문항은 주로:

```text
expected_behavior = refuse
```

로 관리합니다.

---

# 8. evaluate_rag.py

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
RAG 실행
      ↓
Retrieved Context 저장
      ↓
Response 저장
      ↓
run_id / git_commit 기록
      ↓
Result Excel 저장
```

`evaluate_rag.py`는 **점수를 계산하는 Script가 아니라 RAG 실행 결과를 수집하는 Script**입니다.

---

# 9. evaluate_rag.py 실행

Backend와 RAG가 먼저 실행되어 있어야 합니다.

고창:

```bash
python evaluation/evaluate_rag.py \
  --dataset GC \
  --announcement-id 15 \
  --run-id GC_RUN_001
```

서울 번동:

```bash
python evaluation/evaluate_rag.py \
  --dataset BD \
  --announcement-id 4 \
  --run-id BD_RUN_001
```

API:

```text
POST /api/chat
```

Request 예:

```json
{
  "announcementId": 15,
  "question": "신청 기간은 언제인가요?"
}
```

결과 파일 예:

```text
GC_FINAL_V1_RUN_001_result.xlsx
```

---

# 10. evaluate_metrics.py

파일:

```text
evaluation/evaluate_metrics.py
```

역할:

```text
*_result.xlsx 읽기
      ↓
Recall@1 / @3 / @5 계산
      ↓
RAGAS 평가
      ↓
Metric 저장
      ↓
*_scored.xlsx 저장
```

자동 평가를 크게 두 영역으로 나눕니다.

```text
Retrieval
→ Recall@K

Generation
→ RAGAS
```

---

# 11. Recall@K

현재 Retrieval Metric:

```text
Recall@1
Recall@3
Recall@5
```

의미:

```text
Recall@1
→ Top-1 안에 필요한 원문 근거가 있는가

Recall@3
→ Top-3 안에 필요한 원문 근거가 있는가

Recall@5
→ Top-5 안에 필요한 원문 근거가 있는가
```

검색 성능을 대표해서 설명할 때는 주로:

```text
Recall@3
```

를 사용합니다.

---

# 12. 현재 Recall 계산 방식

현재 Recall은 Gold Chunk ID를 직접 비교하지 않고:

```text
reference_text
        ↕
retrieved_contexts
```

를 비교합니다.

방식:

```text
Hybrid Evidence Matching
+
Combined Top-K Context
```

주요 판단 요소:

```text
정규화된 문자열 포함
숫자 일치
핵심 Token 일치
문자열 유사도
복수 Evidence 조합
```

예를 들어 정답에 필요한 정보가 Rank 1과 Rank 2에 나누어져 있어도 Top-3 Context를 결합했을 때 전체 근거가 확인되면 Recall@3 Hit로 판단할 수 있습니다.

Recall 분석용 Column:

```text
recall_match_method
recall_matched_rank
recall_match_score
```

이 값들은 **최종 성능 Metric이 아니라 Recall 판정 이유를 확인하기 위한 진단 정보**입니다.

`reference_text`가 없는 Unanswerable 문항은 Recall 계산 대상에서 제외합니다.

---

# 13. RAGAS 자동 평가

현재 사용하는 주요 RAGAS Metric은 3개입니다.

```text
Faithfulness
Response Relevancy
Factual Correctness
```

## Faithfulness

```text
Response
↕
Retrieved Context
```

검색된 근거에 기반해 답변했는지 평가합니다.

즉, Context에 없는 내용을 임의로 생성했는지 확인합니다.

## Response Relevancy

```text
User Question
↕
Response
```

답변이 질문의 핵심과 얼마나 관련되어 있는지 평가합니다.

## Factual Correctness

```text
Reference
↕
Response
```

생성 답변이 모범 답안과 사실적으로 얼마나 일치하는지 평가합니다.

특히:

```text
숫자
날짜
시간
금액
조건
대상
예외
```

와 같은 정보 오류를 확인하는 데 중요합니다.

---

# 14. 최종 자동 평가 기준

DDOKBOT에서는 최종 정량 성능을 다음 자동 Metric으로 판단합니다.

```text
Retrieval
├─ Recall@1
├─ Recall@3
└─ Recall@5

Generation
├─ Faithfulness
├─ Response Relevancy
└─ Factual Correctness
```

즉:

```text
Recall@K
→ 필요한 근거를 검색했는가?

Faithfulness
→ 검색 근거를 벗어나지 않았는가?

Response Relevancy
→ 질문에 적절하게 답했는가?

Factual Correctness
→ Reference와 사실적으로 일치하는가?
```

를 각각 확인합니다.

---

# 15. evaluate_metrics.py 실행

Recall만 먼저 확인:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --skip-ragas
```

RAGAS 포함 전체 평가:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --ragas-model <MODEL_NAME>
```

특정 RUN 파일을 사용하는 경우:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --xlsx evaluation/results/GC_FINAL_V1_RUN_001_result.xlsx \
  --output evaluation/results/GC_FINAL_V1_RUN_001_scored.xlsx \
  --ragas-model <MODEL_NAME>
```

RAGAS 기본 API:

```text
http://127.0.0.1:8080/v1
```

주요 환경변수:

```text
RAGAS_API_BASE_URL
RAGAS_API_KEY
RAGAS_MODEL
RAGAS_EMBEDDING_MODEL
```

---

# 16. 선택적 재평가

전체 평가를 다시 실행하지 않고 필요한 Metric 또는 문항만 재평가할 수 있습니다.

## Factual Correctness만 실행

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --ragas-model <MODEL_NAME> \
  --factual-only
```

용도:

```text
Factual Correctness 이상값 확인
Judge 모델 변경 테스트
평가 Prompt 테스트
```

---

## 특정 문항만 실행

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --ragas-model <MODEL_NAME> \
  --question-ids Q002,Q003,Q007
```

---

## 한국어 Factual Correctness Prompt 적용

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --ragas-model <MODEL_NAME> \
  --factual-only \
  --adapt-factual-korean
```

조합 예:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --ragas-model <MODEL_NAME> \
  --factual-only \
  --adapt-factual-korean \
  --question-ids Q002,Q003,Q007
```

---

# 17. 챗봇 모델과 Judge 모델

RAG 답변 생성 모델과 RAGAS 평가용 Judge 모델은 같을 필요가 없습니다.

```text
RAG Answer Model
→ 사용자 답변 생성

RAGAS Judge Model
→ 답변 품질 평가
```

Judge 모델에는 실제 서비스 모델보다 더 높은 성능의 모델을 사용할 수 있습니다.

단, RUN 비교에서는 가능한 한 다음을 동일하게 유지합니다.

```text
Judge Model
RAGAS Version
Prompt 설정
평가 Metric
```

그래야 Metric 변화가 실제 RAG 개선 때문인지 평가 조건 변경 때문인지 구분할 수 있습니다.

---

# 18. Human Review

최종 성능 판단은 자동 Metric을 기준으로 합니다.

Human Review의 목적은:

```text
자동 Metric이 낮은 이유 확인
답변의 어떤 정보가 틀렸는지 확인
실패 Stage 분류
자동 평가 이상값 확인
```

입니다.

즉:

```text
Automatic Metric
→ 최종 정량 평가

Human Review
→ 오류 원인 분석
```

주요 Column:

```text
human_score
failure_type
human_comment
```

`human_score` 권장 기준:

```text
2 → 정답
1 → 부분 정답
0 → 오답
```

이 값은 최종 공식 성능 점수보다 **오류 패턴 확인용 보조 정보**로 사용합니다.

---

# 19. Failure Analysis

점수가 낮은 문항은 다음 순서로 확인합니다.

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

핵심:

```text
정답 정보가 마지막으로 정상적으로 존재했던 Stage는 어디인가?
```

대표적인 판단:

| 증상                         | 우선 확인                 |
| -------------------------- | --------------------- |
| 원문에는 있는데 Parsed 결과에 없음     | Parser                |
| 정규화 후 값이 잘못 변경됨            | Normalizer            |
| 제목·표·관계가 깨짐                | Structure             |
| 필요한 정보가 Chunk에서 분리됨        | Chunking              |
| 관련 Chunk가 검색되지 않음          | Embedding / Retrieval |
| Context에는 근거가 있는데 답변이 틀림   | LLM / Prompt          |
| 다른 공고가 검색되거나 Evidence가 누락됨 | DB / API              |

---

# 20. Unanswerable 평가

문서에 없는 질문은 RAG가 임의로 답변하지 않아야 합니다.

예:

```text
주차비는 얼마인가요?
관리비는 얼마인가요?
가장 가까운 지하철역은 어디인가요?
```

문서에 근거가 없다면:

```text
해당 내용은 공고문에서 확인할 수 없습니다.
```

와 같이 답변하는 것이 적절합니다.

필요하면 별도로:

```text
Correct Rejection Rate
```

를 계산할 수 있습니다.

```text
정상 거절한 Unanswerable 질문 수
---------------------------------
전체 Unanswerable 질문 수
```

---

# 21. RUN 관리

RUN은 동일한 평가셋에서 코드나 설정이 달라진 실험 버전을 의미합니다.

예:

```text
GC_RUN_001
→ 개선 전

GC_RUN_002
→ Retrieval 수정 후

GC_RUN_003
→ Prompt 수정 후
```

RUN 비교 시 주요 Metric:

```text
Recall@1
Recall@3
Recall@5

Faithfulness
Response Relevancy
Factual Correctness
```

Human Review는 RUN별 오류 유형 변화 분석에 활용합니다.

---

# 22. Dataset Version과 RUN

평가셋과 RUN은 구분해서 관리합니다.

```text
GC_FINAL_V1.xlsx
→ 평가 질문과 Reference의 버전

GC_RUN_001
→ 시스템 실험 버전
```

코드만 변경했다면:

```text
RUN_001
RUN_002
RUN_003
```

을 증가시킵니다.

평가 질문이나 Reference를 실제로 변경했다면:

```text
GC_FINAL_V2.xlsx
```

처럼 Dataset Version 증가를 검토합니다.

"고정 평가셋"은 모든 문서가 동일한 문항 구성을 가져야 한다는 뜻이 아닙니다.

```text
GC와 BD의 문항 구성
→ 달라도 됨

GC_RUN_001과 GC_RUN_002
→ 같은 GC 평가셋 사용

BD_RUN_001과 BD_RUN_002
→ 같은 BD 평가셋 사용
```

---

# 23. 문서별 결과 비교 주의

문서마다 평가 문항 구성이 다를 수 있으므로 전체 평균만으로 문서 성능을 단순 비교하는 것은 주의해야 합니다.

예를 들어 BD에 Robustness 문항이 10개 포함되어 있고 GC에는 없다면:

```text
GC 93%
BD 88%
```

만 보고 GC가 무조건 더 좋은 성능이라고 판단하기 어렵습니다.

필요하면 다음을 함께 확인합니다.

```text
전체 평균
+
유형별 평균
```

예:

```text
Recall@3 전체       92%

Easy                96%
Medium              91%
Hard                84%
Robustness          87%
```

---

# 24. 전체 평가 실행 순서

```text
1. Backend / RAG 실행 확인
        ↓
2. evaluate_rag.py 실행
        ↓
3. *_result.xlsx 생성
        ↓
4. evaluate_metrics.py --skip-ragas
        ↓
5. Recall 결과 확인
        ↓
6. RAGAS 전체 평가
        ↓
7. *_scored.xlsx 생성
        ↓
8. 자동 Metric 확인
        ↓
9. 낮거나 이상한 문항 Human Review
        ↓
10. Failure Analysis
        ↓
11. 코드 개선
        ↓
12. 다음 RUN 실행
```

---

# 25. 결과 파일 Git 관리

평가 결과는 실행할 때마다 생성되므로 기본적으로 Git에서 제외합니다.

`.gitignore`:

```gitignore
# Evaluation results
evaluation/results/*
!evaluation/results/.gitkeep
```

평가 질문과 Reference가 들어 있는:

```text
evaluation/datasets/
```

은 Source of Truth 역할을 하므로 Git으로 관리합니다.

---

# 26. 핵심 요약

DDOKBOT Evaluation의 핵심 구조:

```text
Dataset
→ 질문 / Reference

evaluate_rag.py
→ RAG 실행 결과 수집

evaluate_metrics.py
→ Recall@K + RAGAS 자동 평가

Automatic Metric
→ 최종 정량 성능 판단

Human Review
→ 낮은 점수의 오류 원인 분석

RUN
→ 코드 수정 전후 비교
```

현재 Retrieval 평가:

```text
Recall@1
Recall@3
Recall@5
```

현재 Recall 방식:

```text
Hybrid Evidence Matching
+
Combined Top-K Context
```

현재 Generation 자동 평가:

```text
Faithfulness
Response Relevancy
Factual Correctness
```

평가셋은 문서별로 유형과 문항 수가 달라도 됩니다.

다만 한 번 고정한 이후에는 동일 문서의 RUN 비교에서 같은 평가 질문과 Reference를 유지합니다.

가장 중요한 원칙:

```text
동일한 평가셋과 동일한 평가 조건을 유지한 상태에서
RUN만 증가시키며 코드 개선 전후의 성능을 비교한다.
```

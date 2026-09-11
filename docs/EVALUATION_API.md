# OneCycle RAG 평가 가이드

> 이 문서는 OneCycle의 평가 데이터 구조, 평가용 DB/서비스 분리, 실제 문서 Pipeline 기반 RAG 답변 생성, Recall/RAGAS 계산, Judge 자원 관리, 재평가와 트러블슈팅 방법을 정리한 문서입니다.
>
> **현재 주 평가 방식은 파일 기반 Fixed RAG가 아니라 `one_cycle_evaluation_tmp` 평가 DB와 평가 전용 Backend/RAG/Document Worker를 사용해 실제 서비스와 동일한 Document Worker → Persistence → Publish → Hybrid Retrieval → Generation 경로를 재현하는 방식입니다.**
>
> 작성 기준
> - Backend / Document Worker / Docker / `evaluate_rag.py` / `dataset_resolver.py` / `evaluate_metrics.py`: `develop-api` 최신 코드 기준

---

# 1. 평가 목적

OneCycle 평가는 단순히 생성 답변 문장만 비교하지 않고 다음 흐름 전체를 확인합니다.

```text
평가 원본 HWP/HWPX
        ↓
평가 DB 등록
        ↓
평가 전용 Document Worker
        ↓
Parser
→ Normalizer
→ Structure / Verification
→ Chunking
→ BGE-M3 Embedding
→ Key Information Extraction
        ↓
Backend Persistence
        ↓
Publish
        ↓
평가 전용 RAG
Vector Search + Keyword Search + RRF
        ↓
Generation LLM
        ↓
response + evidence
        ↓
evaluate_rag.py
        ↓
결과 Excel
        ↓
evaluate_metrics.py
        ↓
Recall@1 / @3 / @5
Faithfulness
Factual Correctness
Correct Rejection

실험/보정 시
→ Answer Quality(PASS / PARTIAL / FAIL)
```

최종 보고에서는 **전체 Q&A 품질 KPI**와 **기술 진단 지표**를 구분합니다.

```text
[최종 Q&A 품질 KPI]
완전일치율
→ (Answer Quality PASS + Correct Rejection 성공) / 전체 문항

부분점수 반영 품질점수
→ (PASS + 0.5 × PARTIAL + Correct Rejection 성공) / 전체 문항

[기술 진단 지표]
검색 근거 포함률       → Recall@3
근거 충실성           → Faithfulness
사실 일치 진단        → Factual Correctness
답변 불가 질문 차단율 → Correct Rejection Rate
```

`Response Relevancy`는 최종 평가에서 제외합니다.

기존 Excel과의 호환 때문에 `response_relevancy` 열은 남아 있을 수 있으나, 현재 `evaluate_metrics.py`는 새 계산에서 이 지표를 실행하지 않습니다.

또한 **현재 `evaluate_metrics.py`는 Response Relevancy용 BGE-M3 / HuggingFaceEmbeddings / sentence-transformers를 로딩하지 않습니다.**

주의할 점은 서비스 Pipeline 자체의 BGE-M3 Embedding과 평가 Metric용 Embedding은 서로 다른 개념이라는 것입니다.

```text
서비스 Pipeline
→ 검색용 BGE-M3 Embedding 사용

현재 evaluate_metrics.py
→ 평가용 Embedding 사용 안 함
→ Judge LLM으로 Faithfulness / Factual Correctness 계산
```

---

# 2. 고정 테스트와 일반화 테스트

## 2.1 고정 테스트

고정 테스트는 개발 중 반복적으로 사용하는 문서와 질문셋입니다.

```text
같은 원본문서
+ 같은 평가 질문
+ 같은 Reference
        ↓
코드 / Prompt 수정 전후 비교
```

주요 용도:

- 문서처리 수정 전후 비교
- Chunking 수정 전후 비교
- Retrieval 수정 전후 비교
- Generation Prompt 수정 전후 비교
- RAGAS Judge Prompt 수정 전후 비교
- `human_score=0/1` 문항 실패 원인 분석
- RUN별 성능 변화 확인

고정 테스트 결과는 튜닝 과정에서 반복적으로 사용되므로 **개발용 성능**으로 구분합니다.

## 2.2 일반화 테스트

고정 평가에 사용하지 않은 새로운 LH 공고문으로 최종 일반화 성능을 확인합니다.

```text
고정 테스트
→ 실패 문항 분석
→ 코드 / Prompt 수정
→ 고정 테스트 재검증
→ 코드 / Prompt 확정
→ 처음 보는 문서로 일반화 테스트
→ 최종 성능 정리
```

일반화 문서를 보고 계속 그 문서에 맞춰 수정하기 시작하면 해당 문서는 사실상 고정 테스트 문서가 되므로 최종 일반화 결과와 분리합니다.

---

# 3. Evaluation 폴더 구조

```text
evaluation/
├── datasets/
│   ├── GC_FINAL_V1.xlsx
│   ├── BD_FINAL_V1.xlsx
│   ├── DH_FINAL_V1.xlsx
│   └── GP_FINAL_V1.xlsx
│
├── source_documents/
│   ├── DOC_GC_001/v1/...
│   ├── DOC_BD_001/v1/...
│   ├── DOC_DH_001/v1/...
│   └── DOC_GP_001/v1/...
│
├── results/
│   └── RAG / Metric 결과 Excel 및 log
│
├── runtime/
│   └── <DATASET>_pipeline.json
│
├── dataset_resolver.py
├── evaluate_rag.py
├── evaluate_metrics.py
│
├── evaluate_rag_fixed.py
├── prepare_fixed_documents.py
└── fixed_rag/
```

`GC`, `BD`, `DH`, `GP`는 현재 사용하는 Dataset 예시일 뿐이며 Dataset 코드를 평가 스크립트에 하드코딩하지 않습니다.
새 Dataset도 아래 이름 규칙만 지키면 동일한 평가 흐름에 추가할 수 있습니다.

```text
평가셋       → evaluation/datasets/<DATASET>_FINAL_V<버전>.xlsx
원본문서 폴더 → evaluation/source_documents/DOC_<DATASET>_<번호>/vN/
RAG 결과     → evaluation/results/<DATASET>_FINAL_V<버전>_ACTUAL_RUN_<번호>_result.xlsx
Metric 결과  → evaluation/results/<DATASET>_FINAL_V<버전>_ACTUAL_RUN_<번호>_scored.xlsx
```

현재 최종 평가의 메인 경로는 다음입니다.

```text
Evaluation DB
→ 실제 Document Worker Pipeline
→ Persistence
→ Publish
→ Hybrid Retrieval
→ Generation
```

다음은 이전 Fixed File 방식이며 최종 메인 평가 경로가 아닙니다.

```text
evaluate_rag_fixed.py
prepare_fixed_documents.py
fixed_rag/
```

---

# 4. 평가 원본문서와 버전 규칙

평가용 문서 ID는 다음 형태를 사용합니다.

```text
DOC_<DATASET>_<번호>
```

예:

```text
DOC_GC_001
DOC_BD_001
DOC_DH_001
DOC_GP_001
```

Excel의 `document_id`와 `evaluation/source_documents/` 아래 폴더명이 동일해야 합니다.

버전 예:

```text
evaluation/source_documents/
└── DOC_DH_001/
    ├── v1/
    │   └── 기존공고.hwpx
    └── v2/
        └── 수정공고.hwpx
```

`dataset_resolver.py`는 가장 높은 `vN`을 선택합니다.

같은 최신 버전에 HWP/HWPX 원본문서가 여러 개 있으면 모호한 입력으로 보고 실패하므로 최신 버전 폴더에는 평가 대상 원본문서를 하나만 둡니다.

`evaluate_rag.py`와 현재 수정된 `evaluate_metrics.py`는 모두 `evaluation/dataset_resolver.py`의 Dataset 규칙을 사용합니다.

따라서 `GC`, `BD`, `DH`, `GP` 같은 Dataset 코드를 각 스크립트의 alias에 계속 추가할 필요가 없습니다.
새 Dataset을 추가할 때는 Dataset ID와 파일/폴더 이름 규칙만 맞추면 됩니다.

Dataset ID에는 영문/숫자와 `.`, `_`, `-`를 사용할 수 있습니다.

예를 들어 새로운 Dataset 코드를 `PT`로 정하면:

```text
evaluation/datasets/PT_FINAL_V1.xlsx
evaluation/source_documents/DOC_PT_001/v1/원본.hwpx
evaluation/results/PT_FINAL_V1_ACTUAL_RUN_001_result.xlsx
```

형태로 관리하고 다음처럼 실행할 수 있습니다.

```bash
python evaluation/evaluate_rag.py \
  --dataset PT \
  --base-url http://127.0.0.1:19000 \
  --run-number 001
```

Metric도 별도 alias 추가 없이 같은 Dataset ID를 사용합니다.

```bash
python evaluation/evaluate_metrics.py \
  --dataset PT \
  --skip-ragas
```


---

# 5. Pipeline Artifact 저장 위치

AWS 프로젝트 위치:

```text
/home/ubuntu/ddokbot/one-cycle_api
```

기본 Host 결과 경로:

```text
/home/ubuntu/ddokbot/one-cycle_api/runtime/outputs/
```

Container 경로:

```text
/app/outputs
```

평가 문서별 구조:

```text
runtime/outputs/
└── DOC_DH_001/
    └── document_<DB_document_id>/
        ├── 01_parsed/
        ├── 02_normalized/
        ├── 03_structured/
        ├── 04_chunks/
        └── 05_embeddings/
```

Embedding Vector는 `embeddings.npy`에 저장되고 부가 정보는 `metadata.json`, `embedding_report.json` 등에 저장됩니다.

---

# 6. 평가 DB와 평가 전용 Docker 구조

운영 DB:

```text
one_cycle
```

평가 DB:

```text
one_cycle_evaluation_tmp
```

평가 데이터는 운영 데이터와 분리합니다.

현재 평가용 Docker Override에서는 다음 세 서비스를 별도로 사용합니다.

| 역할 | Container | Host Port | 내부 연결 |
| --- | --- | --- | --- |
| 평가 Backend | `one-cycle-eval-backend` | `19000` | `eval-rag:18002`, `eval-document-worker:18003` |
| 평가 RAG | `one-cycle-eval-rag` | `19002` | 평가 DB + shared embedding + shared llm |
| 평가 Document Worker | `one-cycle-eval-document-worker` | `19003` | 평가 원본문서 + shared embedding |

공용 서비스:

| 역할 | Container | Host Port |
| --- | --- | --- |
| PostgreSQL | `one-cycle-postgres` | `5432` |
| Embedding | `one-cycle-embedding` | `18001` |
| Generation LLM | `one-cycle-llm` | `8080` |

평가용 Worker는 일반 서비스 Worker와 분리되어 있습니다.

```text
일반 Worker
one-cycle-document-worker
→ 일반 서비스 문서 처리

평가 Worker
one-cycle-eval-document-worker
→ evaluation/source_documents 처리
```

평가 Worker의 주요 mount:

```text
evaluation/source_documents
→ /app/evaluation/source_documents:ro

runtime/outputs
→ /app/outputs
```

---

# 7. 평가 서비스 실행

평가 전용 서비스를 포함해 실행할 때:

```bash
cd ~/ddokbot/one-cycle_api

# 공용 서비스 + 평가 전용 서비스
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.evaluation.yml \
  --profile ai \
  up -d postgres embedding llm eval-document-worker eval-rag eval-backend
```

상태 확인:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

중지된 컨테이너까지 포함:

```bash
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

---

# 8. 평가 원본문서 → 실제 Pipeline 준비

가상환경:

```bash
source ~/ddokbot/venvs/venv/bin/activate
```

평가 DB를 명시하고 평가 Worker를 사용할 때 예:

```bash
POSTGRES_DB=one_cycle_evaluation_tmp \
DOCUMENT_WORKER_BASE_URL=http://127.0.0.1:19003 \
PIPELINE_OUTPUT_HOST_PATH=/home/ubuntu/ddokbot/one-cycle_api/runtime/outputs \
PYTHONPATH=. \
python evaluation/evaluate_rag.py \
  --dataset DH \
  --prepare-only
```

흐름:

```text
평가셋 Excel
→ document_id 확인
→ evaluation/source_documents/DOC_.../<latest version>/
→ Evaluation DB 등록
→ eval-document-worker
→ Parser / Normalizer / Structure / Chunking / Embedding / Key Information
→ Persistence
→ Publish
→ evaluation/runtime/<DATASET>_pipeline.json
```

---

# 9. 실제 RAG 답변 생성

평가용 Backend를 사용할 때는 `19000`을 **명시적으로 지정**합니다.

현재 `evaluate_rag.py`의 실제 `DEFAULT_API_BASE_URL`은 `http://127.0.0.1:18000`이므로,
`--base-url`을 생략하면 평가 전용 Backend(`19000`)가 아니라 일반 Backend(`18000`)를 호출할 수 있습니다.
최종 평가에서는 운영/일반 서비스와 평가 DB가 섞이지 않도록 `--base-url http://127.0.0.1:19000`을 항상 명시합니다.

```bash
POSTGRES_DB=one_cycle_evaluation_tmp \
PYTHONPATH=. \
python evaluation/evaluate_rag.py \
  --dataset DH \
  --base-url http://127.0.0.1:19000 \
  --run-number 001
```

`evaluate_rag.py`는 manifest의 `collection_run_id`를 기준으로 해당 평가 Collection을 Active Collection으로 전환한 뒤 `/api/chat`을 호출합니다.

특정 문항:

```bash
POSTGRES_DB=one_cycle_evaluation_tmp \
PYTHONPATH=. \
python evaluation/evaluate_rag.py \
  --dataset DH \
  --base-url http://127.0.0.1:19000 \
  --run-number 001 \
  --question-ids Q005,Q012,Q020
```

기존 성공 문항까지 강제로 다시 답변 생성:

```bash
POSTGRES_DB=one_cycle_evaluation_tmp \
PYTHONPATH=. \
python evaluation/evaluate_rag.py \
  --dataset DH \
  --base-url http://127.0.0.1:19000 \
  --run-number 001 \
  --question-ids Q005 \
  --rerun-success
```

---

# 10. RAG 답변 생성 시 필요한 자원

실제 RAG 답변 생성은 **RAM만 사용하는 작업이 아닙니다.**

```text
Generation LLM
→ GPU VRAM + 시스템 RAM 사용

BGE-M3 Embedding
→ GPU VRAM + 시스템 RAM 사용 가능

Backend / RAG / PostgreSQL
→ 주로 CPU / RAM 사용
```

따라서 RAG 답변 생성 전에 Judge용 Qwen3가 떠 있다면 먼저 종료하는 것이 좋습니다.

```bash
pkill -TERM -f 'llama-server.*--port 8081'
```

확인:

```bash
pgrep -af 'llama-server.*8081'
```

RAG 답변 생성에 필요한 최소 핵심 서비스는 다음입니다.

```text
postgres
embedding
llm
eval-rag
eval-backend
```

문서처리까지 함께 하면:

```text
eval-document-worker
```

도 필요합니다.

RAM/CPU를 더 확보하고 싶다면 답변 생성에 관계없는 일반 서비스 컨테이너인 `scheduler`, `crawler`, 일반 `document-worker` 등을 팀 사용 여부를 확인한 뒤 중지할 수 있습니다.

단, 공유 AWS라면 다른 팀원의 작업 중인 컨테이너를 임의로 내리지 않습니다.

---

# 11. 결과 Excel 이름 규칙

RAG 답변 결과:

```text
<DATASET>_FINAL_V<버전>_ACTUAL_RUN_<번호>_result.xlsx
```

Metric 결과:

```text
<DATASET>_FINAL_V<버전>_ACTUAL_RUN_<번호>_scored.xlsx
```

현재 수정된 `evaluate_metrics.py`는 `dataset_resolver.py`를 사용해 입력 결과 파일을 찾습니다.

`--xlsx`를 직접 지정하면 해당 파일을 사용합니다.

```bash
python evaluation/evaluate_metrics.py \
  --dataset DH \
  --xlsx evaluation/results/DH_FINAL_V1_ACTUAL_RUN_001_result.xlsx \
  --skip-ragas
```

`--xlsx`를 생략하고 `--dataset`만 지정하면 `evaluation/results/`에서 먼저 다음 패턴을 찾습니다.

```text
<DATASET>_FINAL_V*_ACTUAL_RUN_*_result.xlsx
```

여러 파일이 있으면 **가장 최근 수정된 파일**을 선택합니다.
ACTUAL_RUN 결과가 없으면 일반 `*_result.xlsx` 후보 중 가장 최근 파일을 사용합니다.

`--output`을 생략하면 입력 파일명을 기준으로 scored 파일명을 자동 생성합니다.

```text
DH_FINAL_V1_ACTUAL_RUN_001_result.xlsx
→ DH_FINAL_V1_ACTUAL_RUN_001_scored.xlsx
```

입력 파일명이 `_result.xlsx`로 끝나지 않는 사용자 지정 파일이면 stem 뒤에 `_scored.xlsx`가 붙습니다.

```text
GC_FINAL_프롬프트X.xlsx
→ GC_FINAL_프롬프트X_scored.xlsx
```

`--dataset` 없이 `--xlsx`만 지정할 수도 있습니다. 이 경우 Dataset ID는 파일명에서 추론합니다.
일반적으로 `<DATASET>_FINAL_V...` 규칙을 따르며, 해당 패턴이 아니면 파일명의 첫 번째 `_` 앞 문자열을 Dataset ID로 사용합니다.

Prompt 실험처럼 같은 답변을 사용하면서 Judge 조건만 바꾸는 경우에는 비교가 분명하도록 `--output`을 직접 지정해 별도 이름을 사용할 수 있습니다.

예:

```text
GC_FINAL_프롬프트X.xlsx
GC_FINAL_프롬프트O.xlsx
BD_FINAL_프롬프트X.xlsx
BD_FINAL_프롬프트O.xlsx
```

---

# 12. Excel 주요 열

사람이 작성하는 열:

| 열 | 설명 |
| --- | --- |
| `document_id` | 평가 원본문서 ID |
| `question_id` | 문항 ID |
| `category` | 질문 유형 |
| `difficulty` | 난이도/질문 특성 |
| `user_input` | 실제 질문 |
| `reference` | 사람이 작성한 자연어 모범답안 |
| `required_facts` | Answer Quality에서 반드시 충족해야 하는 필수 정답 목록. 선택 열이지만 V5.1 정밀 평가에서는 작성 권장 |
| `reference_source` | Reference 출처 |
| `reference_text` | 검색되어야 하는 원문 근거. Answer Quality에서는 `SOURCE_EVIDENCE`로도 사용 |
| `expected_behavior` | `answer` 또는 `refuse` |
| `human_score` | 2 / 1 / 0 |
| `failure_type` | 실패 원인 |
| `human_comment` | 수동 분석 메모 |

`required_facts`는 기존 Excel에 없어도 실행이 깨지지 않도록 `evaluate_metrics.py`가 열을 자동 생성합니다.
셀 값이 비어 있으면 해당 문항의 `reference`를 자동으로 대신 사용합니다.

```text
required_facts 값 있음
→ 해당 값을 Answer Quality 필수 정답 기준으로 사용

required_facts 값 없음
→ reference를 required_facts로 폴백
```

하위 호환을 위한 폴백이므로 **V5.1 Answer Quality를 최종 기준으로 사용할 경우에는 문항별 `required_facts`를 명시적으로 작성하는 것이 권장됩니다.**

`evaluate_rag.py`가 채우는 대표 열:

| 열 | 설명 |
| --- | --- |
| `retrieved_chunk_ids` | 검색 Chunk ID |
| `retrieved_contexts` | Rank 순 실제 검색 Context |
| `response` | 챗봇 답변 |
| `run_id` | 평가 실행 식별자 |
| `git_commit` | 실행 당시 commit |
| `git_branch` | 실행 당시 branch |
| `grounded` | API grounded 값 |
| `evidence` | API evidence JSON |
| `embedding_model` | 서비스 검색용 Embedding Model |
| `elapsed_ms` | API 처리 시간 |

`evaluate_metrics.py`가 계산/추가하는 주요 열:

| 열 | 설명 |
| --- | --- |
| `recall_at_1` | Top-1 근거 포함 여부 |
| `recall_at_3` | Top-3 근거 포함 여부 |
| `recall_at_5` | Top-5 근거 포함 여부 |
| `faithfulness` | 답변이 Retrieved Context에 근거하는지 |
| `factual_correctness` | 답변과 Reference의 사실 일치 정도 |
| `correct_rejection` | Unanswerable 정상 거절 여부 |
| `rejection_match_reason` | 거절 판정 근거 |
| `recall_match_method` | Recall 매칭 방식 |
| `recall_matched_rank` | 근거 Rank |
| `recall_match_score` | Recall 진단 점수 |
| `ragas_status` | Metric 실행 상태 |
| `response_relevancy` | 과거 호환용. 현재 계산 안 함 |
| `answer_quality` | 실험용 PASS/PARTIAL/FAIL 판정 |
| `answer_quality_reason` | Answer Quality 사유 |
| `answer_quality_status` | Answer Quality 실행 상태 |
| `answer_quality_human_match` | Human Score와의 판정 일치 여부 |

---

# 13. Recall@K 평가 방식

Recall은 고정 Chunk ID가 아니라 다음을 비교합니다.

```text
reference_text
        ↕
retrieved_contexts
```

판정에는 다음 정보가 사용됩니다.

- 숫자 일치율
- 핵심 Token Coverage
- 부분 문자열 유사도
- 복합 Evidence

복합질문은 각 Context 개별 확인 후 실패하면 Top-K Context를 합쳐 다시 검사합니다.

최종 KPI는 `Recall@3`를 사용하고 `Recall@1`, `Recall@5`는 진단용으로 함께 기록합니다.

---

# 14. Correct Rejection

`expected_behavior=refuse` 또는 `unanswerable` 문항은 답변 불가 질문입니다.

```text
correct_rejection = 1
→ 정상 거절

correct_rejection = 0
→ 문서에 없는 내용을 답함
```

현재는 응답에서 다음과 같은 거절 표현을 탐지합니다.

```text
확인할 수 없습니다
확인되지 않습니다
찾을 수 없습니다
문서에서 확인할 수 없습니다
공고문에서 확인할 수 없습니다
해당 정보가 없습니다
근거를 찾을 수 없습니다
답변할 수 없습니다
알 수 없습니다
```

Correct Rejection Rate:

```text
정상 거절 문항 수 / 전체 Unanswerable 문항 수
```

Unanswerable 문항은 Faithfulness / Factual Correctness / Answer Quality 계산에서 제외하고 Correct Rejection으로 별도 평가합니다.

---

# 15. 현재 Factual Correctness 설정

현재 `evaluate_metrics.py`는 RAGAS `FactualCorrectness`를 다음 옵션으로 설정할 수 있습니다.

```text
--factual-mode
  f1
  precision
  recall

--factual-atomicity
  low
  high

--factual-coverage
  low
  high
```

기본값:

```text
mode       = f1
atomicity  = low
coverage   = low
```

의미:

```text
f1
→ 응답 사실의 정확성과 Reference 핵심 사실 포함 범위를 종합

precision
→ 응답이 말한 사실이 정확한지 중심

recall
→ Reference 핵심 사실이 응답에 얼마나 포함됐는지 중심
```

`atomicity=high`는 날짜·시간·금액·조건을 더 작은 claim으로 세분화하는 실험에 사용할 수 있습니다.

Prompt 효과만 비교할 때는 atomicity/coverage/mode를 동시에 바꾸지 않고 동일하게 고정하는 것이 좋습니다.

---

# 16. Factual Correctness 한국어 Adaptation

기본 RAGAS Factual Correctness Prompt를 한국어로 adaptation하려면:

```text
--adapt-factual-korean
```

이 옵션은 다음 두 Prompt를 한국어로 adaptation합니다.

```text
claim decomposition prompt
NLI prompt
```

비교 실험에서 프로젝트 보완 Prompt의 효과만 보고 싶다면 **기존 실험과 보완 실험 둘 다 `--adapt-factual-korean`을 사용**하고 `--use-project-factual-prompt` 적용 여부만 다르게 둡니다.

---

# 17. OneCycle Factual Correctness 보완 Prompt

현재 `develop-api` 최신 코드에는 다음 옵션이 있습니다.

```text
--use-project-factual-prompt
```

보완 기준은 claim 분해와 NLI 판정을 분리해서 적용합니다.

## 17.1 Claim 분해 기준

주요 원칙:

- 주택형, 공급계층, 대상, 날짜, 시작/종료 시간, 금액, 비율, 기간, 모집 인원, 자격 조건, 예외 조건, 가능/불가능 결론을 가능한 한 독립적인 사실 단위로 분리
- 하나의 claim에는 하나의 대상과 하나의 핵심 사실만 포함
- 날짜와 시간, 기본값과 전환값, 일반 기준과 예외 기준을 섞지 않음
- 원문에 실제로 적힌 사실만 추출

## 17.2 NLI 사실 일치 기준

주요 원칙:

- 표면 문자열보다 의미, 대상, 조건, 핵심 값을 비교
- 날짜·시간·금액은 단위를 정규화해 비교
- 표현·어순·존댓말·조사·띄어쓰기 차이만으로 감점하지 않음
- 핵심 사실이 긴 답변의 중간/마지막에 있어도 인정
- 추가 설명이 핵심 정답과 모순되지 않으면 감점하지 않음
- 대상이나 조건이 다르면 숫자가 같아도 불일치
- 기본 기준과 예외 기준, 기본 임대료와 전환 임대료, 서류 대상자 발표와 최종 당첨자 발표 등을 구분
- 최종 가능/불가능, 초과/이하 결론이 틀리면 불일치

즉 Human Score와 Factual Correctness 차이가 크게 나는 문제를 줄이기 위해 다음 기준을 명시적으로 보완했습니다.

```text
모범답안 핵심 사실이 포함되면 표현이 달라도 정답 인정
날짜·금액·자격 조건 등 핵심 값 일치를 우선 확인
문장 길이·어순·동의 표현 차이만으로 감점하지 않음
핵심 조건이 달라지면 문맥이 비슷해도 오답 처리
```

---

# 18. Answer Quality 실험 지표

현재 `develop-api` 최신 `evaluate_metrics.py`에는 Factual Correctness와 별도로 Human 판정과의 정렬을 확인하기 위한 **실험용 Answer Quality**가 포함되어 있습니다.

현재 코드의 Answer Quality Prompt 버전은:

```text
V5.1-AUTO-GUARDRAILS
```

이며 실행 시 다음 로그로 실제 적용 버전을 확인할 수 있습니다.

```text
[RAGAS] Answer Quality 프롬프트 적용: V5.1-AUTO-GUARDRAILS
```

현재 문서 기준으로 Answer Quality는 아직 최종 KPI가 아니라 **Human Score와 Judge 판정 차이를 보정·분석하기 위한 지표**로 둡니다.
최종 KPI로 채택할 경우에는 Prompt 버전, 자동 보정 규칙, `required_facts` 값까지 함께 고정해야 합니다.

옵션:

```text
--answer-quality
→ 기존 Faithfulness / Factual Correctness와 함께 실행

--answer-quality-only
→ Faithfulness / Factual Correctness는 실행하지 않고 Answer Quality만 실행
```

결과:

```text
PASS
PARTIAL
FAIL
```

Human Score 매핑:

```text
PASS    ↔ human_score 2
PARTIAL ↔ human_score 1
FAIL    ↔ human_score 0
```

`answer_quality_human_match`에 Human Score와의 정확 일치 여부를 1/0으로 기록합니다.

## 18.1 V5.1 입력 구조

V5.1 Answer Quality는 단순히 `REFERENCE`와 `RESPONSE`만 비교하지 않습니다.

```text
QUESTION
→ 사용자가 실제로 물은 질문

REQUIRED_FACTS
→ 질문에 반드시 답해야 하는 필수 정답 목록

REFERENCE
→ 사람이 작성한 자연어 모범답안

SOURCE_EVIDENCE
→ 사람이 지정한 원문 근거(reference_text)

RESPONSE
→ 평가할 챗봇 답변
```

판정 우선순위는 다음과 같습니다.

```text
필수 답변의 범위 / 누락 여부
→ REQUIRED_FACTS 기준

자연어 의미 / 질문 맥락
→ REFERENCE 보조

추가 설명의 사실 여부
→ SOURCE_EVIDENCE(reference_text) 보조

검색 결과
→ retrieved_contexts를 Answer Quality의 정답 기준으로 사용하지 않음
```

`required_facts`가 비어 있으면 하위 호환을 위해 `reference`를 자동으로 사용하지만,
정밀 평가에서는 `required_facts`를 문항별로 명시하는 것이 좋습니다.

## 18.2 PASS / PARTIAL / FAIL 핵심 기준

```text
PASS
→ REQUIRED_FACTS의 핵심 사실과 결론이 모두 정확
→ 잘못된 추가 설명이나 상충 조건 없음

PARTIAL
→ 올바른 핵심 사실이 하나 이상 존재
→ 일부 누락 / 모호한 결론 / 잘못 연결된 대상·조건 / 틀린 추가 설명이 함께 존재

FAIL
→ 질문에 필요한 핵심 사실이 하나도 정확하지 않음
→ 반대 결론만 제시
→ 다른 대상·계층·주택형·일정의 사실만 답함
→ 정답이 있는데 확인할 수 없다고만 답함
```

답변이 길거나 부가 설명이 있다는 이유만으로 감점하지 않습니다.
추가 설명을 감점하려면 실제로 틀린 값, 잘못된 대상·조건 또는 핵심 정답과의 충돌이 확인되어야 합니다.

## 18.3 V5.1 자동 Guardrail

LLM Judge가 반환한 PASS/PARTIAL/FAIL 뒤에 `apply_answer_quality_guardrails()`가 **객관적으로 확인 가능한 일부 모순만 규칙 기반으로 보정**합니다.

현재 자동 보정 대상은 다음과 같습니다.

```text
1. 명시적 답변 거절
   - 일부 핵심 사실은 맞고 나머지만 확인 불가 → PARTIAL
   - 핵심 정답을 확인 불가라고 답함 → FAIL

2. 원 / 만원 환산
   - 정규화한 금액은 같은데 Judge가 단위 변환 오류로 FAIL 판정
   → 다른 오류 가능성을 보존하기 위해 PARTIAL까지만 복원

3. 필수 시간 누락
   - REQUIRED_FACTS에 있는 시간이 RESPONSE에 없는데 Judge가 PASS
   → PARTIAL

4. 신청 자격 과단정
   - 다른 자격도 함께 충족해야 하는데 일부 조건만 보고 신청 가능을 단정
   → PASS를 PARTIAL로 보정

5. 금융인증서 / 공동인증서 안내 충돌
   - 관련 질문에서 모바일 사용 설명과 공동인증서 복사 조건이 상충
   → PARTIAL

6. Judge 판정 사유와 PASS의 자기모순
   - reason에 실제 누락·오류를 명시하면서 label은 PASS
   → PARTIAL
```

자동 보정이 적용되면 `answer_quality_reason` 끝에 다음 형식이 추가됩니다.

```text
[AUTO_GUARDRAIL] ...
```

따라서 Answer Quality 오판을 분석할 때는 최종 label만 보지 말고 `answer_quality_reason`의 원래 Judge 사유와 `[AUTO_GUARDRAIL]` 내용을 함께 확인합니다.

## 18.4 정규화 Answer Quality 점수

실행 종료 시 PASS/PARTIAL/FAIL 개수와 함께 정규화 품질점수를 출력합니다.

```text
정규화 품질점수
= (PASS 개수 + 0.5 × PARTIAL 개수) / 전체 Answer Quality 판정 개수
```

즉:

```text
PASS    = 1.0
PARTIAL = 0.5
FAIL    = 0.0
```

으로 환산한 평균입니다.

또한 `human_score`가 존재하면:

```text
PASS    ↔ 2
PARTIAL ↔ 1
FAIL    ↔ 0
```

기준으로 `휴먼 판정 일치율`도 출력합니다.

## 18.5 옵션 조합 제한

다음 옵션 조합은 사용할 수 없습니다.

```text
--answer-quality-only + --answer-quality
--factual-only + Answer Quality 옵션
--skip-ragas + Answer Quality 옵션
```

`--answer-quality-only`여도 Recall@1/@3/@5는 기존 Metric 처리 흐름에 따라 다시 계산됩니다.
Answerable에서는 Answer Quality를 계산하고, Unanswerable에서는 Answer Quality를 건너뛰고 Correct Rejection을 계산합니다.

---

# 19. Dataset 자동 탐색과 새 Dataset 추가

현재 수정된 `evaluate_metrics.py`는 더 이상 `GC`, `BD` 같은 Dataset alias를 코드에 하드코딩하지 않습니다.

기존 구조:

```text
normalize_dataset_name()
→ GC / BD alias 직접 관리
→ 새 Dataset마다 코드 수정 필요
```

현재 구조:

```text
evaluation/dataset_resolver.py
→ normalize_dataset_id()
→ resolve_result_xlsx()
→ default_scored_path()
```

즉 `evaluate_rag.py`와 `evaluate_metrics.py`가 같은 Dataset 규칙을 사용합니다.

## 19.1 `--dataset`만 지정하는 경우

예:

```bash
python evaluation/evaluate_metrics.py \
  --dataset DH \
  --skip-ragas
```

동작:

```text
evaluation/results/
→ DH_FINAL_V*_ACTUAL_RUN_*_result.xlsx 탐색
→ 가장 최근 수정된 파일 선택
→ ACTUAL_RUN 결과가 없으면 DH_FINAL_V*_result.xlsx 후보 탐색
→ --output이 없으면 *_scored.xlsx 자동 생성
```

따라서 다음 Dataset은 모두 같은 코드 경로를 사용합니다.

```bash
python evaluation/evaluate_metrics.py --dataset GC --skip-ragas
python evaluation/evaluate_metrics.py --dataset BD --skip-ragas
python evaluation/evaluate_metrics.py --dataset DH --skip-ragas
python evaluation/evaluate_metrics.py --dataset GP --skip-ragas
```

새 Dataset `PT`도 Metric 코드를 수정하지 않고 사용할 수 있습니다.

```bash
python evaluation/evaluate_metrics.py \
  --dataset PT \
  --skip-ragas
```

## 19.2 `--xlsx`를 직접 지정하는 경우

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --xlsx evaluation/results/GC_FINAL_프롬프트X.xlsx \
  --output evaluation/results/GC_FINAL_프롬프트O.xlsx \
  --skip-ragas
```

이 경우 자동 탐색 대신 지정한 Excel을 그대로 사용합니다.

`--dataset` 없이 `--xlsx`만 사용하는 것도 가능합니다.

```bash
python evaluation/evaluate_metrics.py \
  --xlsx evaluation/results/DH_FINAL_V1_ACTUAL_RUN_001_result.xlsx \
  --skip-ragas
```

Dataset ID는 파일명에서 추론합니다.

```text
DH_FINAL_V1_ACTUAL_RUN_001_result.xlsx → DH
GC_FINAL_프롬프트X.xlsx               → GC
```

## 19.3 새 Dataset 추가 규칙

새 공고를 평가할 때 평가 코드에 alias를 추가하지 말고 다음 규칙을 맞춥니다.

```text
Dataset ID
→ 예: PT

평가셋
→ evaluation/datasets/PT_FINAL_V1.xlsx

Excel document_id
→ DOC_PT_001

원본문서
→ evaluation/source_documents/DOC_PT_001/v1/원본.hwpx

RAG 결과
→ evaluation/results/PT_FINAL_V1_ACTUAL_RUN_001_result.xlsx

Metric 결과
→ evaluation/results/PT_FINAL_V1_ACTUAL_RUN_001_scored.xlsx
```

따라서 **새 Dataset 추가 시 수정해야 하는 것은 평가 데이터와 파일/폴더 이름이며, `evaluate_rag.py`나 `evaluate_metrics.py`의 Dataset alias 코드는 수정하지 않습니다.**

---

# 20. Recall만 계산

평가용 가상환경:

```bash
source ~/ddokbot/venvs/eval_venv/bin/activate
```

GC 예:

```bash
PYTHONPATH=. \
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --xlsx evaluation/results/GC_FINAL_V1_ACTUAL_RUN_001_result.xlsx \
  --output evaluation/results/GC_FINAL_V1_ACTUAL_RUN_001_scored.xlsx \
  --skip-ragas
```

`--skip-ragas`에서는 Qwen Judge가 필요하지 않습니다.

---

# 21. RAGAS 실행 전 GPU / RAM 확인

RAGAS Judge를 띄우기 전에 자원 확인을 권장합니다.

RAM:

```bash
free -h
```

GPU:

```bash
nvidia-smi
```

컨테이너 상태:

```bash
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

컨테이너별 자원 사용:

```bash
docker stats --no-stream
```

실시간 GPU 확인:

```bash
watch -n 1 nvidia-smi
```

실시간 RAM 확인:

```bash
watch -n 1 free -h
```

---

# 22. GPU 메모리 확보 방법

Metric 계산은 이미 생성된 Excel을 읽고 Judge Qwen3에 요청하는 작업이므로 **서비스용 Generation LLM이나 Embedding 서비스가 필요하지 않습니다.**

GPU VRAM이 많이 사용 중이면 먼저 `nvidia-smi`에서 PID와 프로세스를 확인합니다.

가장 먼저 확인할 컨테이너는 일반적으로:

```text
one-cycle-llm
```

입니다.

실제 테스트에서도 서비스 LLM 컨테이너가 GPU VRAM과 RAM을 동시에 크게 사용했습니다.

RAGAS Metric만 계산하는 동안 서비스 답변 생성이 필요 없다면:

```bash
docker stop one-cycle-llm
```

추가 GPU 여유가 필요하면:

```bash
docker stop one-cycle-embedding
```

도 고려할 수 있습니다.

`one-cycle-rag` 자체는 보통 LLM/Embedding 모델처럼 큰 VRAM을 직접 점유하는 주체는 아니므로, **GPU 확보 목적이라면 `llm` → `embedding` 순서로 먼저 확인**하는 것이 좋습니다.

평가 전용 Backend/RAG/Worker도 Metric 계산에는 필요하지 않으므로 해당 작업을 사용하지 않는 시간에는 중지할 수 있습니다.

예:

```bash
docker stop \
  one-cycle-eval-backend \
  one-cycle-eval-rag \
  one-cycle-eval-document-worker
```

다만 공유 서버에서는 다른 사람의 작업 여부를 먼저 확인합니다.

---

# 23. Qwen3 RAGAS Judge 백그라운드 실행

현재 사용 명령:

```bash
nohup /home/ubuntu/tools/llama.cpp/build/bin/llama-server \
  -hf Qwen/Qwen3-14B-GGUF:Q4_K_M \
  --host 127.0.0.1 \
  --port 8081 \
  -ngl 99 \
  -c 8192 \
  -ctk q8_0 \
  -ctv q8_0 \
  --jinja \
  --chat-template-kwargs '{"enable_thinking":false}' \
  > evaluation/results/qwen_judge_8081.log 2>&1 \
  < /dev/null &
```

옵션 의미:

```text
-ngl 99
→ 가능한 Layer를 GPU에 offload

-c 8192
→ llama.cpp context window

-ctk q8_0 / -ctv q8_0
→ KV cache 관련 quantization 설정

--jinja
→ 모델의 Jinja Chat Template 사용

--chat-template-kwargs '{"enable_thinking":false}'
→ Qwen3의 불필요하게 긴 thinking/reasoning 출력을 억제
```

Judge 실행 확인:

```bash
pgrep -af 'llama-server.*8081'
```

API 확인:

```bash
curl -sS http://127.0.0.1:8081/v1/models
```

Judge 로그:

```bash
tail -f evaluation/results/qwen_judge_8081.log
```

GPU/RAM 재확인:

```bash
free -h
nvidia-smi
```

---

# 24. RAGAS 전체 평가 포그라운드 실행

BD 예:

```bash
source ~/ddokbot/venvs/eval_venv/bin/activate

PYTHONPATH=. \
python evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_scored.xlsx \
  --output evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --adapt-factual-korean
```

이 경우 Answerable 문항에서 기본적으로 다음을 계산합니다.

```text
Recall@1 / @3 / @5
Faithfulness
Factual Correctness
```

Unanswerable은 Correct Rejection으로 계산합니다.

---

# 25. RAGAS 전체 평가 백그라운드 실행

백그라운드 실행은 Python 출력이 로그에 즉시 기록되도록 **`python -u`를 사용**합니다.

```bash
nohup env PYTHONPATH=. \
python -u evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_scored.xlsx \
  --output evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --adapt-factual-korean \
  > evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.log 2>&1 &
```

로그 확인:

```bash
tail -f evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.log
```

`tail -f`에서 `Ctrl + C`를 눌러도 로그 보기만 종료되며 백그라운드 평가 프로세스는 계속 실행됩니다.

평가 프로세스 확인:

```bash
ps -ef | grep evaluate_metrics.py | grep -v grep
```

---

# 26. Resume / 기존 값 Skip / 강제 재계산

현재 `evaluate_metrics.py`는 **Metric 단위 자동 Resume**을 지원합니다.

핵심 동작은 다음과 같습니다.

```text
--rerun-success 없음
→ 이미 값이 있는 RAGAS Metric은 유지
→ 비어 있는 RAGAS Metric만 계산
→ 중단 후 다시 실행해도 완료된 Metric을 다시 Judge에 보내지 않음

--rerun-success 있음
→ 요청된 RAGAS Metric은 기존 값이 있어도 다시 계산
→ 새 결과로 덮어씀
```

## 26.1 기존 값이 있을 때 실제 동작

현재 코드에서 자동 Skip 대상은 다음 RAGAS 계열 Metric입니다.

```text
faithfulness
factual_correctness
answer_quality
```

예를 들어 한 문항이 다음 상태라면:

```text
faithfulness       = 0.92
factual_correctness = 빈칸
answer_quality      = PASS
```

`--rerun-success` 없이 일반 RAGAS 평가를 실행하면:

```text
faithfulness
→ 기존 0.92 유지 / SKIP

factual_correctness
→ 비어 있으므로 새로 계산

answer_quality
→ --answer-quality 옵션을 사용했다면 기존 PASS 유지 / SKIP
```

즉 **기존에 정상 값이 있으면 그대로 두고 비어 있는 부분만 채우는 방식**입니다.

다만 모든 열이 Skip되는 것은 아닙니다.

```text
Recall@1 / Recall@3 / Recall@5
→ 선택되어 처리되는 문항에서는 항상 다시 계산

Correct Rejection
→ 선택되어 처리되는 문항에서는 항상 다시 판정

response_relevancy
→ 현재 최종 평가에서 사용하지 않으므로 처리된 문항은 빈칸으로 유지

Faithfulness / Factual Correctness / Answer Quality
→ 기존 값 존재 여부 + 실행 옵션에 따라 Resume/Skip
```

따라서 `--rerun-success`는 **Recall 재계산 여부를 제어하는 옵션이 아니라 RAGAS 성공 Metric을 강제로 다시 계산할지 결정하는 옵션**으로 이해하면 됩니다.

## 26.2 출력 파일이 이미 있는 경우

출력 파일이 이미 존재하고 `--rerun-success`를 사용하지 않으면:

```text
기존 output.xlsx를 Resume Source로 다시 읽음
→ 완료된 Metric 값 유지
→ 비어 있는 Metric만 계산
→ 문항마다 즉시 다시 저장
```

로그 예:

```text
[RESUME] 기존 출력 파일에서 이어서 평가합니다.
[RESUME] faithfulness 기존 값 유지
[RESUME] factual_correctness 기존 값 유지
[RESUME] 요청한 RAGAS metric이 이미 존재 → RAGAS SKIP
```

중간에 평가가 끊겼다가 같은 명령을 다시 실행하는 경우 이 동작을 사용하면 됩니다.

## 26.3 기존 값까지 새 값으로 덮어쓰기

기존 성공값까지 강제로 새 기준으로 다시 계산하려면:

```text
--rerun-success
```

을 사용합니다.

예:

```bash
nohup env PYTHONPATH=. \
python -u evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --output evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --answer-quality-only \
  --rerun-success \
  > evaluation/results/BD_answer_quality_rerun.log 2>&1 &
```

이 경우:

```text
Answer Quality
→ 기존 PASS/PARTIAL/FAIL 값이 있어도 새로 계산하여 덮어씀

Faithfulness / Factual Correctness
→ --answer-quality-only이므로 다시 계산하지 않음

Recall@1/3/5
→ 다시 계산

Correct Rejection
→ Unanswerable 문항에서 다시 판정
```

## 26.4 `--rerun-success` 사용 시 입력 파일 주의

중요한 동작:

```text
--rerun-success 없음
→ output이 이미 있으면 output을 Resume Source로 사용

--rerun-success 있음
→ 지정한 input(--xlsx)을 기준으로 다시 계산
```

따라서 **기존 output의 Human Score, Human Comment, 일부 수동 수정값 등을 그대로 유지하면서 일부 문항만 강제 재평가하려면 `--xlsx`와 `--output`을 같은 최신 파일로 지정하는 것이 가장 안전합니다.**

예:

```bash
python evaluation/evaluate_metrics.py \
  --dataset GC \
  --xlsx evaluation/results/GC_ANSWER_QUALITY_V5_1_FULL.xlsx \
  --output evaluation/results/GC_ANSWER_QUALITY_V5_1_FULL.xlsx \
  --answer-quality-only \
  --rerun-success \
  --question-ids Q013,Q016
```

이렇게 하면 선택한 문항만 새 Answer Quality 값으로 덮어쓰고, 선택하지 않은 다른 문항과 Human Review 값은 그대로 유지됩니다.

## 26.5 실패/누락 문항만 이어서 계산

기존 성공값을 건드리지 않고 실패하거나 비어 있는 문항만 이어서 계산하려면 `--rerun-success`를 넣지 않습니다.

```bash
nohup env PYTHONPATH=. \
python -u evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --output evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --adapt-factual-korean \
  --question-ids Q001,Q003,Q006,Q017,Q032 \
  > evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final_retry.log 2>&1 &
```

정리:

```text
기존 값 유지 + 빈칸만 채우기
→ --rerun-success 사용 안 함

기존 값 무시 + 새 기준으로 다시 계산
→ --rerun-success 사용

특정 문항만 처리
→ --question-ids 사용

기존 파일을 그대로 보존하며 일부만 강제 재계산
→ --xlsx와 --output을 같은 최신 파일로 지정
```

---

# 27. Factual Correctness만 재평가

Faithfulness는 건드리지 않고 Factual Correctness만 다시 계산할 때:

```text
--factual-only
```

을 사용합니다.

예:

```bash
nohup env PYTHONPATH=. \
python -u evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --output evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --adapt-factual-korean \
  --factual-only \
  --rerun-success \
  --question-ids Q001,Q008,Q013 \
  > evaluation/results/BD_factual_retry.log 2>&1 &
```

이 경우 선택 문항의 기존 Factual Correctness 값이 있어도 다시 계산합니다.

---

# 28. Prompt X / Prompt O 비교

Human Score와 Factual Correctness가 크게 차이난 문항만 보완 Prompt로 재계산할 때 사용합니다.

기존 파일:

```text
GC_FINAL_프롬프트X.xlsx
BD_FINAL_프롬프트X.xlsx
```

## GC 12문항

```bash
nohup env PYTHONPATH=. \
python -u evaluation/evaluate_metrics.py \
  --dataset GC \
  --xlsx evaluation/results/GC_FINAL_프롬프트X.xlsx \
  --output evaluation/results/GC_FINAL_프롬프트O.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --adapt-factual-korean \
  --use-project-factual-prompt \
  --factual-only \
  --rerun-success \
  --question-ids Q014,Q016,Q019,Q025,Q027,Q030,Q031,Q033,Q035,Q038,Q041,Q052 \
  > evaluation/results/GC_FINAL_프롬프트O.log 2>&1 &
```

## BD 19문항

```bash
nohup env PYTHONPATH=. \
python -u evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_프롬프트X.xlsx \
  --output evaluation/results/BD_FINAL_프롬프트O.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --adapt-factual-korean \
  --use-project-factual-prompt \
  --factual-only \
  --rerun-success \
  --question-ids Q001,Q008,Q013,Q014,Q016,Q017,Q020,Q026,Q029,Q030,Q035,Q037,Q048,Q054,Q055,Q063,Q064,Q069,Q070 \
  > evaluation/results/BD_FINAL_프롬프트O.log 2>&1 &
```

이 실험에서는:

```text
Human Score / Human Comment
→ 그대로 유지

Faithfulness
→ 재계산 안 함

Factual Correctness
→ 선택 문항만 프로젝트 Prompt로 강제 재계산
```

Prompt 효과만 비교하려면 `factual-mode`, `atomicity`, `coverage`, Judge Model 등 다른 조건은 X/O에서 동일하게 유지합니다.

---

# 29. Answer Quality만 빠르게 실험

Human Score 불일치 문항을 PASS/PARTIAL/FAIL 방식으로 직접 비교하려면:

```bash
nohup env PYTHONPATH=. \
python -u evaluation/evaluate_metrics.py \
  --dataset BD \
  --xlsx evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_Final.xlsx \
  --output evaluation/results/BD_FINAL_V1_ACTUAL_RUN_001_AnswerQuality.xlsx \
  --ragas-base-url http://127.0.0.1:8081/v1 \
  --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M" \
  --answer-quality-only \
  --rerun-success \
  --question-ids Q001,Q008,Q013 \
  > evaluation/results/BD_answer_quality.log 2>&1 &
```

Answer Quality는 현재 문서 기준으로 최종 KPI가 아니라 Human Score와 Judge 판정 차이를 분석하기 위한 보조 실험입니다.

`--answer-quality-only --rerun-success`로 전체 문항을 실행하면:

```text
Recall@1 / Recall@3 / Recall@5
→ 다시 계산

Answer Quality
→ Answerable 문항에서 기존 값이 있어도 다시 계산

Faithfulness
→ 계산하지 않음 / 기존 값 유지

Factual Correctness
→ 계산하지 않음 / 기존 값 유지

Correct Rejection
→ Unanswerable 문항에서 다시 판정
```

전체 문항을 V5.1 기준으로 다시 계산할 때는 `--question-ids`를 생략합니다.

예:

```bash
nohup env PYTHONPATH=. python -u evaluation/evaluate_metrics.py   --dataset DH   --xlsx evaluation/results/DH_ANSWER_QUALITY_CALIBRATION_V3_FINAL.xlsx   --output evaluation/results/DH_ANSWER_QUALITY_V5_1_FULL.xlsx   --ragas-base-url http://127.0.0.1:8081/v1   --ragas-model "Qwen/Qwen3-14B-GGUF:Q4_K_M"   --answer-quality-only   --rerun-success   > evaluation/results/DH_ANSWER_QUALITY_V5_1_FULL.log 2>&1 &
```

로그 시작부에서 다음을 확인합니다.

```text
평가 모드       : Answer Quality only
Answer Quality  : 실행
선택 문항       : 전체
```

그리고 Judge 로그에는 다음 Prompt 버전이 보여야 합니다.

```text
[RAGAS] Answer Quality 프롬프트 적용: V5.1-AUTO-GUARDRAILS
```

---

# 30. Judge 종료와 서비스 복구

Judge 종료:

```bash
pkill -TERM -f 'llama-server.*--port 8081'
```

확인:

```bash
pgrep -af 'llama-server.*8081'
```

서비스 복구가 필요하면:

```bash
cd ~/ddokbot/one-cycle_api

docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.evaluation.yml \
  --profile ai \
  up -d postgres embedding llm eval-document-worker eval-rag eval-backend
```

일반 서비스 Worker/Backend/RAG도 필요하면 별도로 다시 시작합니다.

---

# 31. 트러블슈팅

## 31.1 `Connection error`

대표 메시지:

```text
<last_exception>
    Connection error.
</last_exception>
```

Judge가 8081에 떠 있는지 확인합니다.

```bash
pgrep -af 'llama-server.*8081'
ss -ltnp | grep 8081
curl -sS http://127.0.0.1:8081/v1/models
```

Judge 로그:

```bash
tail -n 100 evaluation/results/qwen_judge_8081.log
```

평가 프로세스가 `Exit 1`로 끝났다면 Judge를 정상 실행한 뒤 실패 문항만 다시 계산합니다.

---

## 31.2 `max_tokens length limit`

대표 메시지:

```text
The output is incomplete due to a max_tokens length limit.
```

Faithfulness는 최종 Excel에는 0~1 값 하나만 저장되지만 내부에서는:

```text
response
→ claim 분해
→ 각 claim과 retrieved_contexts 비교
→ claim별 지원 여부 판정
→ 최종 0~1 계산
```

과정을 거치기 때문에 Context와 Judge reasoning 길이의 영향을 받습니다.

Qwen3가 긴 `reasoning_content`를 생성하지 않도록 현재 Judge 실행에서는:

```text
--jinja
--chat-template-kwargs '{"enable_thinking":false}'
```

를 사용합니다.

현재 `-c 8192`를 사용하므로 **입력 Prompt 자체가 8192 token을 넘는 문항은 여전히 실패할 수 있습니다.**

이 경우 처리 우선순위:

```text
1. 실제 Judge 실행 옵션에 enable_thinking=false가 들어갔는지 확인
2. 실패 문항만 --question-ids로 재시도
3. GPU 여유가 있을 때만 context window 증가 검토
4. retrieved_contexts를 임의로 줄이는 것은 Faithfulness 판정 근거 자체를 바꿀 수 있으므로 마지막 수단
```

실제 실행 옵션 확인:

```bash
ps -ef | grep llama-server | grep -v grep
```

---

## 31.3 GPU가 이미 많이 사용 중

```bash
nvidia-smi
```

먼저 `one-cycle-llm`을 확인합니다.

```bash
docker ps --format "{{.Names}}" | grep -E 'llm|embedding'
```

Metric만 계산한다면:

```bash
docker stop one-cycle-llm
```

추가로 필요하면:

```bash
docker stop one-cycle-embedding
```

그 후 다시:

```bash
free -h
nvidia-smi
```

으로 자원을 확인한 뒤 Qwen Judge를 실행합니다.

---

## 31.4 RAM 부족 / Swap 증가

확인:

```bash
free -h
```

프로세스별 RAM:

```bash
ps -p <PID> -o pid,cmd,%mem,rss,vsz
```

RSS를 GiB로 확인:

```bash
ps -p <PID> -o rss= | awk '{printf "%.2f GiB\n", $1/1024/1024}'
```

서비스 LLM은 GPU뿐 아니라 RAM도 크게 사용할 수 있습니다.

Metric 계산 중이라면 서비스 LLM/Embedding을 내리고 Judge만 띄우는 방식이 안정적입니다.

RAG 답변 생성 중이라면 반대로 Judge를 종료하고 서비스 `llm`, `embedding`, `eval-rag`, `eval-backend`에 자원을 우선 배정합니다.

---

## 31.5 `Exit 127`

`nohup` 명령이 잘못 끊겼거나 명령/경로를 찾지 못할 때 발생할 수 있습니다.

확인:

```bash
which python
ls -l evaluation/evaluate_metrics.py
```

특히 로그 리다이렉션 파일명이 줄바꿈으로 분리되지 않았는지 확인합니다.

정상 예:

```text
> evaluation/results/BD_retry.log 2>&1 &
```

---

## 31.6 `tail -f`에 `nohup: ignoring input`만 보임

정상 메시지일 수 있습니다.

Python 버퍼링 때문에 로그가 늦게 기록될 수 있으므로 백그라운드 Metric 실행은:

```text
python -u
```

를 사용합니다.

프로세스가 실제 살아 있는지 확인:

```bash
ps -ef | grep evaluate_metrics.py | grep -v grep
```

---

## 31.7 이전 로그를 잘못 보고 있는 경우

실행한 로그 파일과 `tail -f` 대상이 같은지 확인합니다.

예:

```text
실행 출력
GC_FINAL_프롬프트O.log

잘못 확인
BD_FINAL_프롬프트O.log
```

로그 파일 목록:

```bash
ls -lh evaluation/results/*.log
```

---

## 31.8 Resume했는데 기존 값이 덮어써짐

강제 재실행 옵션을 확인합니다.

```text
--rerun-success
```

이 옵션이 있으면 선택 문항의 기존 성공 Metric도 다시 계산합니다.

기존 값이 있는 문항을 자동 Skip하려면 `--rerun-success`를 빼야 합니다.

---

## 31.9 Factual Prompt 비교인데 Faithfulness까지 다시 계산됨

Prompt 차이만 비교할 때는 반드시:

```text
--factual-only
```

를 사용합니다.

그리고 기존 Factual 값이 있어도 새 Prompt로 다시 계산하려면:

```text
--rerun-success
```

를 함께 사용합니다.

---

## 31.10 Dataset 결과 파일을 찾지 못함

현재 Metric 코드는 Dataset alias 제한 대신 `dataset_resolver.py`의 파일 탐색 규칙을 사용합니다.

대표 오류:

```text
평가 결과 Excel을 찾을 수 없습니다.
먼저 evaluate_rag.py를 실행하거나 --xlsx를 지정하세요.
```

먼저 결과 파일을 확인합니다.

```bash
ls -lh evaluation/results/
```

Dataset ID가 `DH`라면 자동 탐색 대상은 우선 다음 형식입니다.

```text
DH_FINAL_V*_ACTUAL_RUN_*_result.xlsx
```

파일명이 규칙과 다르거나 Prompt 실험용 사용자 지정 파일을 쓰는 경우에는 `--xlsx`를 직접 지정합니다.

```bash
python evaluation/evaluate_metrics.py \
  --dataset DH \
  --xlsx evaluation/results/원하는파일.xlsx \
  --skip-ragas
```

새 Dataset에서 예전처럼 `지원하지 않는 dataset` 오류가 나온다면 현재 수정본이 아니라 **이전 GC/BD alias 버전의 `evaluate_metrics.py`가 실행되고 있을 가능성**이 큽니다.

현재 코드 확인:

```bash
grep -n "normalize_dataset_name\|resolve_result_xlsx" \
  evaluation/evaluate_metrics.py
```

현재 수정본은 `resolve_result_xlsx()`를 사용하고, GC/BD만 허용하는 `normalize_dataset_name()` alias 로직은 없어야 합니다.

---

## 31.11 Answer Quality 판정이 Human Score와 다름

먼저 다음 열을 같은 문항에서 함께 확인합니다.

```text
user_input
required_facts
reference
reference_text
response
answer_quality
answer_quality_reason
human_score
human_comment
```

확인 순서:

```text
1. required_facts가 질문이 요구한 필수 사실만 포함하는지 확인
2. required_facts가 비어 reference로 폴백된 문항인지 확인
3. response에 필수값이 실제로 존재하는지 확인
4. answer_quality_reason의 원래 Judge 사유 확인
5. [AUTO_GUARDRAIL]이 붙었다면 어떤 규칙이 label을 보정했는지 확인
6. 마지막으로 human_score 자체가 일관된 기준으로 매겨졌는지 검토
```

코드의 현재 Prompt 버전 확인:

```bash
grep -n "ANSWER_QUALITY_PROMPT_VERSION"   evaluation/evaluate_metrics.py
```

현재 V5.1 기준:

```text
V5.1-AUTO-GUARDRAILS
```

최종 기준을 동결한 뒤에는 Prompt, Guardrail 로직 또는 `required_facts`를 변경하면
기존 Answer Quality 결과와 직접 비교할 수 없으므로 해당 지표를 다시 계산해야 합니다.

---

# 32. 오답 원인 분석 순서

권장 순서:

```text
1. user_input
2. required_facts / reference / reference_text
3. 실제 원본문서
4. 01_parsed
5. 02_normalized
6. 03_structured
7. 04_chunks
8. DB Chunk / Embedding
9. retrieved_contexts
10. Recall@3
11. response
12. Faithfulness / Factual Correctness / Correct Rejection
13. Answer Quality / answer_quality_reason / AUTO_GUARDRAIL
14. RAGAS Judge Prompt / Judge 출력
```

해석 예:

```text
Recall@3 = 0
→ 필요한 근거 검색 실패
→ Retrieval / Chunking / 문서처리 확인

Recall@3 = 1 + 답변 오류
→ 검색 근거는 있음
→ Generation / Prompt 확인

Human Score는 높은데 Factual Correctness가 낮음
→ Judge Prompt / claim decomposition / NLI 판정 기준 확인

Unanswerable인데 답변함
→ Correct Rejection 실패
→ Generation 거절 정책 확인
```

---

# 33. RUN / Prompt 비교 시 기록할 조건

다음 조건을 기록합니다.

```text
Dataset Version
원본문서 Version
Git Branch
Git Commit
Generation Model
Embedding Model
Judge Model
Judge context(-c)
Judge thinking 설정
Retrieval 방식
Top-K
RRF 설정
Generation Prompt
Factual Prompt
Factual mode
Factual atomicity
Factual coverage
Answer Quality Prompt Version
Answer Quality Guardrail Version/코드
required_facts 기준
Recall 판정 기준
Run ID
```

Prompt 비교에서는 여러 조건을 동시에 바꾸지 않는 것이 중요합니다.

예:

```text
실험 A
--adapt-factual-korean

실험 B
--adapt-factual-korean
--use-project-factual-prompt
```

이렇게 해야 프로젝트 보완 Prompt 자체의 영향을 해석하기 쉽습니다.

Answer Quality를 RUN 간 비교할 때도 같은 원칙을 적용합니다.

```text
동일하게 고정
→ Judge Model
→ ANSWER_QUALITY_PROMPT_VERSION
→ AUTO_GUARDRAIL 로직
→ required_facts
→ Human Score 기준

하나라도 변경
→ 이전 Answer Quality와 동일 기준이 아니므로 재계산 필요
```

---

# 34. 권장 자원 사용 흐름

```text
[1] 실제 평가 답변 생성

postgres
embedding
llm
eval-document-worker
eval-rag
eval-backend
        ↓
evaluate_rag.py
        ↓
result.xlsx

[2] 답변 생성 완료

서비스 LLM / Embedding 등
Metric 계산에 필요 없는 GPU 서비스 중지
        ↓
free -h
nvidia-smi
        ↓
GPU/RAM 확보

[3] Judge 실행

Qwen3 :8081
-c 8192
thinking=false
        ↓
evaluate_metrics.py
        ↓
Recall@3
Faithfulness
Factual Correctness
Correct Rejection

[4] Judge 종료
        ↓
서비스 Docker 복구
```

---

# 35. 최소 코드 검증

Metric 코드 문법 검사:

```bash
source ~/ddokbot/venvs/eval_venv/bin/activate

python -m py_compile evaluation/evaluate_metrics.py
```

Import 확인:

```bash
python -c "import evaluation.evaluate_metrics; print('evaluate_metrics import OK')"
```

CLI 옵션 확인:

```bash
python evaluation/evaluate_metrics.py --help
```

다음 최신 옵션이 보이는지 확인합니다.

```text
--factual-only
--factual-mode
--factual-atomicity
--factual-coverage
--answer-quality
--answer-quality-only
--rerun-success
--question-ids
--adapt-factual-korean
--use-project-factual-prompt
```

Dataset Resolver 적용 여부 확인:

```bash
grep -n "normalize_dataset_name\|resolve_result_xlsx" \
  evaluation/evaluate_metrics.py
```

현재 수정본에서는 `resolve_result_xlsx()`가 사용되고, GC/BD만 허용하는 `normalize_dataset_name()` alias 로직은 없어야 합니다.

Answer Quality V5.1 적용 여부 확인:

```bash
grep -n "ANSWER_QUALITY_PROMPT_VERSION\|apply_answer_quality_guardrails\|required_facts"   evaluation/evaluate_metrics.py
```

현재 코드에서는 다음이 확인되어야 합니다.

```text
ANSWER_QUALITY_PROMPT_VERSION = "V5.1-AUTO-GUARDRAILS"
apply_answer_quality_guardrails(...)
required_facts
```

---

# 36. 최종 KPI 계산 방법

최종 평가에서는 지표를 두 층으로 나눠 사용합니다.

```text
[최종 서비스 품질 KPI]
1. 완전일치율
2. 부분점수 반영 품질점수

[원인 분석 / 기술 진단 지표]
- Recall@3
- Faithfulness
- Factual Correctness
- Correct Rejection Rate
```

즉 최종 Q&A 품질을 하나의 문항 단위 성공률로 볼 때는
**Answerable 문항의 Answer Quality와 Unanswerable 문항의 Correct Rejection을 합쳐 계산**합니다.

현재 코드에서는:

```text
Answerable
→ Answer Quality로 PASS / PARTIAL / FAIL 평가

Unanswerable
→ Answer Quality는 실행하지 않음
→ Correct Rejection으로 1 / 0 평가
```

하므로 두 유형을 하나의 최종 품질 KPI로 합치는 것이 가능합니다.

`Response Relevancy`는 최종 평가에서 제외합니다.

---

## 36.1 최종 KPI 1 — 완전일치율

완전일치율은 **완전히 정답으로 인정된 문항의 비율**입니다.

Answerable 문항에서는:

```text
Answer Quality = PASS
→ 1점

Answer Quality = PARTIAL
→ 0점

Answer Quality = FAIL
→ 0점
```

Unanswerable 문항에서는:

```text
Correct Rejection = 1
→ 1점

Correct Rejection = 0
→ 0점
```

계산식:

```text
완전일치율
= (Answer Quality PASS 수 + Correct Rejection 성공 수)
  / 전체 문항 수
× 100
```

여기서:

```text
전체 문항 수
= Answerable 문항 수 + Unanswerable 문항 수
```

예:

```text
전체 문항        = 60
Answerable       = 55
Unanswerable     = 5

PASS             = 43
PARTIAL          = 8
FAIL             = 4

Correct Rejection 성공 = 4
Correct Rejection 실패 = 1
```

완전일치율:

```text
(43 + 4) / 60 × 100
= 78.33%
```

즉 60개 질문 가운데 **완전하게 성공한 질문이 47개**라는 의미입니다.

이 지표는 가장 엄격한 최종 Q&A 성공률입니다.

---

## 36.2 최종 KPI 2 — 부분점수 반영 품질점수

PARTIAL 문항을 완전 실패로 처리하면
핵심 정답 일부를 맞춘 답변과 완전히 틀린 답변을 동일하게 0점 처리하게 됩니다.

이를 보완하기 위해 PARTIAL에 0.5점을 주는
**부분점수 반영 품질점수**를 함께 계산합니다.

점수 규칙:

```text
Answerable

PASS
→ 1.0점

PARTIAL
→ 0.5점

FAIL
→ 0점


Unanswerable

Correct Rejection 성공
→ 1.0점

Correct Rejection 실패
→ 0점
```

계산식:

```text
부분점수 반영 품질점수
= (PASS 수
   + 0.5 × PARTIAL 수
   + Correct Rejection 성공 수)
  / 전체 문항 수
× 100
```

같은 예를 사용하면:

```text
PASS                   = 43
PARTIAL                = 8
FAIL                   = 4
Correct Rejection 성공 = 4
전체 문항              = 60
```

계산:

```text
(43 + 0.5 × 8 + 4) / 60 × 100

= (43 + 4 + 4) / 60 × 100
= 51 / 60 × 100
= 85.0%
```

따라서 같은 평가 결과라도:

```text
완전일치율
→ 78.33%

부분점수 반영 품질점수
→ 85.0%
```

처럼 나타날 수 있습니다.

두 값의 차이는 **PARTIAL 답변이 얼마나 존재하는지**를 보여주는 참고 정보가 됩니다.

---

## 36.3 '부분일치율'이라는 표현 주의

두 번째 계산식은 엄밀히 말하면 단순한 `PARTIAL 비율`이 아니라
**PARTIAL에 0.5 가중치를 준 전체 품질점수**입니다.

따라서 최종 보고에서는 다음 명칭을 권장합니다.

```text
완전일치율
부분점수 반영 품질점수
```

단순 PARTIAL 비율이 필요한 경우에는 별도로:

```text
PARTIAL 비율
= PARTIAL 수 / Answerable 문항 수 × 100
```

로 계산할 수 있지만,
이 값 자체를 최종 KPI로 사용하지는 않습니다.

---

## 36.4 왜 Correct Rejection을 최종 KPI에 합치는가

Unanswerable 문항은 정답 내용을 생성하는 것이 목표가 아니라
**문서에 없는 내용을 답하지 않고 정상적으로 거절하는 것 자체가 정답**입니다.

따라서 최종 Q&A 품질에서는:

```text
Answerable
→ PASS가 완전 성공

Unanswerable
→ Correct Rejection 성공이 완전 성공
```

으로 동일하게 1점 처리합니다.

이렇게 해야 전체 평가셋의 모든 문항이 최종 KPI의 분모에 포함됩니다.

예를 들어:

```text
Answerable 55문항
Unanswerable 5문항
총 60문항
```

이면 최종 완전일치율과 부분점수 반영 품질점수의 분모는 모두 `60`입니다.

---

## 36.5 Answer Quality 정규화 점수와 최종 품질점수의 차이

코드가 출력하는 기존 Answer Quality 정규화 점수는
**Answer Quality가 실행된 Answerable 문항만** 대상으로 합니다.

계산식:

```text
Answer Quality 정규화 점수
= (PASS 수 + 0.5 × PARTIAL 수)
  / (PASS + PARTIAL + FAIL)
× 100
```

반면 최종 서비스 품질 KPI는 Unanswerable까지 포함합니다.

```text
부분점수 반영 품질점수
= (PASS 수
   + 0.5 × PARTIAL 수
   + Correct Rejection 성공 수)
  / 전체 문항 수
× 100
```

따라서 두 값을 혼동하면 안 됩니다.

예:

```text
Answerable = 55
PASS       = 43
PARTIAL    = 8
FAIL       = 4

Answer Quality 정규화 점수
= (43 + 0.5 × 8) / 55
= 47 / 55
= 85.45%
```

Unanswerable까지 포함하면:

```text
Correct Rejection 성공 = 4
전체 문항              = 60

최종 부분점수 반영 품질점수
= (43 + 0.5 × 8 + 4) / 60
= 51 / 60
= 85.0%
```

즉:

```text
Answer Quality 정규화 점수
→ Answerable 답변 품질만 평가

최종 부분점수 반영 품질점수
→ Answerable + Unanswerable를 모두 포함한 전체 Q&A 품질 KPI
```

입니다.

---

## 36.6 Excel에서 최종 KPI 계산

필요한 열:

```text
question_id
expected_behavior
answer_quality
correct_rejection
```

현재 코드 구조에서는 보통:

```text
Answerable 문항
→ answer_quality에 PASS / PARTIAL / FAIL
→ correct_rejection은 N/A

Unanswerable 문항
→ answer_quality는 평가 Skip
→ correct_rejection에 1 / 0
```

으로 저장됩니다.

### 완전일치율

개념식:

```text
(PASS 개수 + correct_rejection=1 개수)
÷ 전체 question_id 개수
× 100
```

Excel 개념식:

```excel
=(COUNTIF(answer_quality범위,"PASS")
  +COUNTIF(correct_rejection범위,1))
 /COUNTA(question_id범위)
```

셀에 `%` 서식을 적용하면 됩니다.

### 부분점수 반영 품질점수

개념식:

```text
(PASS 개수
 + 0.5 × PARTIAL 개수
 + correct_rejection=1 개수)
÷ 전체 question_id 개수
× 100
```

Excel 개념식:

```excel
=(COUNTIF(answer_quality범위,"PASS")
  +0.5*COUNTIF(answer_quality범위,"PARTIAL")
  +COUNTIF(correct_rejection범위,1))
 /COUNTA(question_id범위)
```

역시 셀에 `%` 서식을 적용합니다.

---

## 36.7 더 안전한 Excel 계산 — expected_behavior까지 확인

과거 결과 파일이나 수동 수정 파일에서는
Unanswerable 행에 오래된 `answer_quality` 값이 남아 있을 가능성을 배제하기 어렵습니다.

최종 발표 수치를 계산할 때는 `expected_behavior`까지 조건에 넣는 방식이 더 안전합니다.

예:

```text
Answerable
expected_behavior = answer

Unanswerable
expected_behavior = refuse 또는 unanswerable
```

완전일치율 개념:

```text
(
  answer 문항 중 PASS 수
  +
  refuse/unanswerable 문항 중 correct_rejection=1 수
)
÷ 전체 문항 수
```

부분점수 반영 품질점수:

```text
(
  answer 문항 중 PASS 수
  +
  0.5 × answer 문항 중 PARTIAL 수
  +
  refuse/unanswerable 문항 중 correct_rejection=1 수
)
÷ 전체 문항 수
```

이 방식이 최종 발표 수치 계산에는 가장 권장됩니다.

---

## 36.8 최종 KPI와 기술 진단 지표의 관계

최종 서비스 품질 KPI:

```text
완전일치율
부분점수 반영 품질점수
```

이 두 값은 최종 사용자의 관점에서
**전체 질문 중 얼마나 제대로 처리했는지**를 보여줍니다.

반면 다음 지표들은 원인 분석용입니다.

```text
Recall@3
→ 필요한 검색 근거를 Top-3 안에 가져왔는가

Faithfulness
→ 생성 답변이 검색된 Context에 근거했는가

Factual Correctness
→ 생성 답변과 Reference의 사실이 얼마나 일치하는가

Correct Rejection Rate
→ Unanswerable만 따로 봤을 때 정상 거절 비율은 얼마인가
```

따라서 최종 발표에서는 다음처럼 구분해서 제시할 수 있습니다.

```text
[최종 Q&A 품질]
완전일치율                  XX.X%
부분점수 반영 품질점수     XX.X%

[세부 진단]
Recall@3                   XX.X%
Faithfulness               XX.X%
Factual Correctness        XX.X%
Correct Rejection Rate     XX.X%
```

이렇게 하면 전체 품질과 실패 원인을 동시에 설명할 수 있습니다.

---

## 36.9 Recall@3 계산

검색된 Top-3 Context 안에 정답 근거가 포함되었는지를 평가합니다.

```text
Recall@3
= recall_at_3가 1인 Answerable 문항 수
  / Recall 평가가 가능한 Answerable 문항 수
× 100
```

현재 코드에서는 `Recall@1`, `Recall@3`, `Recall@5`를 모두 계산하지만
최종 검색 KPI는 `Recall@3`을 사용합니다.

---

## 36.10 Faithfulness 계산

```text
Faithfulness
= 유효한 faithfulness 값의 합
  / 유효한 faithfulness 값 개수
× 100
```

Unanswerable 문항은 제외합니다.

Judge 실패 등으로 값이 비어 있는 문항은 평균에서 제외되므로
최종 발표 수치 확정 전에 누락값이 없는지 확인해야 합니다.

---

## 36.11 Factual Correctness 계산

```text
Factual Correctness
= 유효한 factual_correctness 값의 합
  / 유효한 factual_correctness 값 개수
× 100
```

Unanswerable 문항은 제외합니다.

Factual Correctness는 Answer Quality와 평가 목적이 다릅니다.

```text
Factual Correctness
→ RAGAS claim/NLI 기반 사실 일치 진단

Answer Quality
→ 질문이 실제로 요구한 필수 사실을 기준으로 PASS/PARTIAL/FAIL 판정
```

따라서 Human Score와의 정렬을 확인하는 데는 Answer Quality를 사용하고,
Factual Correctness는 RAGAS 기반 진단 지표로 함께 기록합니다.

---

## 36.12 Correct Rejection Rate 계산

```text
Correct Rejection Rate
= correct_rejection = 1인 문항 수
  / 전체 Unanswerable 문항 수
× 100
```

이 값은 최종 완전일치율/부분점수 반영 품질점수에도 포함되지만,
Unanswerable 대응 성능 자체를 따로 확인하기 위해 별도 지표로도 기록합니다.

예:

```text
Unanswerable 5문항
정상 거절 4문항

Correct Rejection Rate
= 4 / 5
= 80.0%
```

---

## 36.13 여러 문서의 최종 종합 KPI

GC / BD / DH / GP처럼 여러 문서를 평가할 때는
**문서별 수치와 전체 통합 수치를 둘 다 기록**하는 것이 좋습니다.

### 문서별

각 문서에서:

```text
완전일치율
부분점수 반영 품질점수
Recall@3
Faithfulness
Factual Correctness
Correct Rejection Rate
```

를 각각 계산합니다.

### 전체 통합 Q&A KPI

전체 평가 문항을 하나로 합쳐 최종 Q&A KPI를 계산할 수도 있습니다.

예:

```text
전체 PASS 수
+ 전체 Correct Rejection 성공 수
--------------------------------
전체 문항 수
```

이 방식은 모든 문항을 직접 합산하므로 **Micro 방식**입니다.

완전일치율:

```text
전체 완전일치율
= (전체 PASS 수 + 전체 Correct Rejection 성공 수)
  / 전체 문항 수
× 100
```

부분점수 반영 품질점수:

```text
전체 부분점수 반영 품질점수
= (전체 PASS 수
   + 0.5 × 전체 PARTIAL 수
   + 전체 Correct Rejection 성공 수)
  / 전체 문항 수
× 100
```

### 문서 평균

문서별 성능을 같은 비중으로 비교하려면 Macro Average를 같이 사용할 수 있습니다.

```text
Macro
→ 문서별 KPI를 동일 가중치로 평균

Micro
→ 모든 문항을 직접 합산
```

최종 Q&A KPI는 공식 자체가 **전체 문항 수를 분모로 정의**되어 있으므로
전체 평가셋 통합 결과를 제시할 때는 **Micro 방식의 완전일치율과 부분점수 반영 품질점수를 우선값으로 사용**하는 것이 자연스럽습니다.

문서 간 일반화 성능을 비교할 때는 Macro 평균을 함께 제시합니다.

---

## 36.14 최종 KPI 계산 전 필수 검증

완전일치율과 부분점수 반영 품질점수는
모든 문항이 정상적으로 판정되어 있어야 의미가 있습니다.

최종 계산 전에 확인:

```text
Answerable 문항
→ answer_quality가 PASS / PARTIAL / FAIL 중 하나인지

Unanswerable 문항
→ correct_rejection이 0 / 1인지

누락 Answer Quality
→ 없어야 함

누락 Correct Rejection
→ 없어야 함
```

중요:

```text
Judge 실패로 answer_quality가 빈칸
→ 0점으로 간주하지 않음
→ 먼저 재평가하여 값을 채운 뒤 KPI 계산

Correct Rejection 미계산
→ 0점으로 간주하지 않음
→ 먼저 재계산 후 KPI 계산
```

즉 **평가 실패와 실제 품질 실패를 같은 0점으로 처리하지 않습니다.**

누락값이 있으면 Resume 기능으로 빈칸을 먼저 채웁니다.

---

## 36.15 최종 기준 동결

최종 KPI 비교에서는 다음 기준을 끝까지 동일하게 유지해야 합니다.

```text
Answer Quality Prompt Version
→ V5.1-AUTO-GUARDRAILS

AUTO_GUARDRAIL 로직
→ 동일 코드

required_facts
→ 동일 기준

PASS / PARTIAL / FAIL 정의
→ 동일 기준

PARTIAL 가중치
→ 0.5 고정

Correct Rejection 판정 기준
→ 동일 REFUSAL_PATTERNS / 동일 코드

Judge Model
→ 동일 모델

Judge context / thinking 설정
→ 동일 설정
```

이 중 하나라도 바꾸면 이전 결과와 동일 기준의 KPI가 아니므로
영향을 받는 문항 또는 전체 평가를 다시 계산해야 합니다.

최종 발표에서는 다음 두 값을 **최종 Q&A 품질 KPI**로 사용합니다.

```text
완전일치율
= (PASS + Correct Rejection 성공)
  / 전체 문항
× 100

부분점수 반영 품질점수
= (PASS + 0.5 × PARTIAL + Correct Rejection 성공)
  / 전체 문항
× 100
```

그리고 다음 값은 **기술 진단 지표**로 함께 제시합니다.

```text
Recall@3
Faithfulness
Factual Correctness
Correct Rejection Rate
```

보조 분석:

```text
Human Score / Human Comment
Human ↔ Answer Quality 일치율
Recall@1 / Recall@5
recall_match_method
ragas_status
```

---

# 37. 핵심 요약

```text
평가 원본문서
→ evaluation/source_documents/DOC_<DATASET>_001/vN/

평가 질문셋
→ evaluation/datasets/<DATASET>_FINAL_V*.xlsx

실제 Pipeline Artifact
→ /home/ubuntu/ddokbot/one-cycle_api/runtime/outputs/

평가 DB
→ one_cycle_evaluation_tmp

평가 서비스
→ eval-document-worker :19003
→ eval-rag             :19002
→ eval-backend         :19000

RAG 답변
→ evaluation/results/*_result.xlsx

Metric
→ Recall@3
→ Faithfulness
→ Factual Correctness
→ Correct Rejection

RAGAS Judge
→ Qwen3-14B-GGUF:Q4_K_M
→ 127.0.0.1:8081
→ -c 8192
→ thinking=false

현재 evaluate_metrics.py
→ Response Relevancy 계산 안 함
→ 평가용 Embedding 로딩 안 함
→ Dataset alias 하드코딩 없음
→ dataset_resolver.py로 GC / BD / DH / GP 및 새 Dataset 처리
→ Resume 지원: 기존 성공 RAGAS Metric 유지, 빈칸만 계산
→ --rerun-success: 기존 성공 RAGAS Metric도 강제 재계산/덮어쓰기
→ --use-project-factual-prompt 지원
→ Answer Quality V5.1 실험 지원
→ REQUIRED_FACTS / SOURCE_EVIDENCE 기반 판정
→ V5.1 AUTO_GUARDRAIL 적용
```

현재 OneCycle 평가에서 가장 중요한 원칙:

1. 평가 원본문서는 운영 DB가 아니라 `one_cycle_evaluation_tmp`를 사용합니다.
2. 최종 평가는 실제 서비스와 동일한 문서처리 / Persistence / Hybrid Retrieval / Generation 경로를 사용합니다.
3. 평가 Document Worker/RAG/Backend는 일반 서비스용과 분리합니다.
4. RAG 답변 생성과 RAGAS Judge 실행을 분리해 GPU/RAM을 관리합니다.
5. Metric 계산 전에 `free -h`, `nvidia-smi`로 자원을 확인합니다.
6. GPU 확보가 필요하면 Metric 단계에서 우선 `one-cycle-llm`, 필요 시 `one-cycle-embedding`을 중지합니다.
7. RAG 답변 생성은 RAM만 사용하는 작업이 아니며 LLM/Embedding이 GPU와 RAM을 함께 사용할 수 있습니다.
8. Prompt 비교는 다른 조건을 동일하게 고정하고 필요한 문항만 재계산합니다.
9. 새 Dataset은 평가 코드에 alias를 추가하지 않고 `<DATASET>_FINAL_V*`, `DOC_<DATASET>_*` 이름 규칙으로 관리합니다.
10. `evaluate_rag.py`와 `evaluate_metrics.py`는 `dataset_resolver.py`의 Dataset 규칙을 공유합니다.
11. 최종 평가용 RAG 답변 생성에서는 일반 Backend로 잘못 연결되지 않도록 `--base-url http://127.0.0.1:19000`을 명시합니다.
12. Answer Quality 비교에서는 Prompt Version, AUTO_GUARDRAIL, `required_facts`를 동일하게 고정합니다.
13. 최종 Q&A 품질 KPI는 `완전일치율`과 `부분점수 반영 품질점수`입니다.
14. 완전일치율은 `(PASS + Correct Rejection 성공) / 전체 문항`으로 계산합니다.
15. 부분점수 반영 품질점수는 `(PASS + 0.5 × PARTIAL + Correct Rejection 성공) / 전체 문항`으로 계산합니다.
16. 전체 평가셋 통합 Q&A KPI는 전체 문항을 직접 합산하는 Micro 값을 우선 사용하고, 문서 간 일반화 비교에는 Macro 평균을 함께 기록합니다.
17. Recall@3, Faithfulness, Factual Correctness, Correct Rejection Rate는 기술 진단 지표로 함께 제시합니다.
18. 최종 KPI 확정 전 Answer Quality와 Correct Rejection의 누락/실패값이 없는지 확인합니다.
19. Response Relevancy는 제외합니다.

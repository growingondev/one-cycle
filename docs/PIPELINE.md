# DDOKBOT Document Pipeline

> 이 문서는 DDOKBOT의 HWP/HWPX 문서 처리 Pipeline을 설명합니다.
>
> 새로운 개발자 또는 AI가 이 문서만 읽고도 다음 내용을 이해할 수 있도록 작성되었습니다.
>
> - 원본 문서를 어디에 넣는지
> - Pipeline을 어떻게 실행하는지
> - 각 Stage가 어떤 파일을 호출하는지
> - 각 Stage의 입력과 출력이 무엇인지
> - 결과가 어디에 저장되는지
> - 최종적으로 PostgreSQL까지 어떻게 연결되는지
> - 특정 Stage만 수정할 때 어디까지 영향을 받는지

---

# 1. Pipeline 목적

DDOKBOT의 Document Pipeline은 원본 HWP/HWPX 공고문을 RAG에서 검색 가능한 데이터로 변환합니다.

전체 처리 흐름:

```text
HWP / HWPX
    ↓
Parser
    ↓
Normalized Document
    ↓
Structure
    ↓
Chunks
    ↓
Embeddings
    ↓
Persistence
    ↓
PostgreSQL + pgvector
```

Runtime Chat은 이 Pipeline을 매 질문마다 실행하지 않습니다.

Pipeline은 사전에 문서를 처리하여 DB에 저장하는 **Ingestion 과정**입니다.

---

# 2. Pipeline Entry Point

전체 Pipeline의 상위 실행 파일:

```text
/home/ubuntu/ddokbot/one-cycle/run_pipeline.py
```

프로젝트 Root:

```text
/home/ubuntu/ddokbot/one-cycle
```

프로젝트 Python:

```text
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python
```

일반 실행 위치:

```bash
cd /home/ubuntu/ddokbot/one-cycle
```

---

# 3. Pipeline Stage 순서

현재 Pipeline은 다음 순서로 구성됩니다.

```text
parse
  ↓
normalize
  ↓
structure
  ↓
chunk
  ↓
embed
  ↓
persist
```

각 단계별 주요 실행 파일:

| Stage | 실행 파일 |
|---|---|
| Parse | `pipeline/parser/hwp_parser.py`, `pipeline/parser/hwpx_parser.py` |
| Normalize | `pipeline/normalizer/document_normalizer.py` |
| Structure | `pipeline/structure/run_structure.py` |
| Chunk | `pipeline/chunking/run_chunking.py` |
| Embed | `pipeline/embedding/run_embeddings.py` |
| Persist | `backend/app/services/pipeline_persistence.py` |

---

# 4. Test Input Documents

현재 Pipeline 검증용 원본 문서는 다음 위치에 있습니다.

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

각 공고 디렉터리 안에는 HWP/HWPX 원본 파일이 들어갈 수 있습니다.

예:

```text
tests/fixtures/documents/
└── announcement_001/
    ├── example.hwp
    └── example.hwpx
```

현재 `run_pipeline.py`는 이 Fixture 구조를 기준으로 테스트 문서를 탐색합니다.

실제 운영 Crawler가 구현되면 원본 파일 전달 방식은 달라질 수 있지만,
Pipeline 단계 자체의 입력 계약은 유지하는 것이 좋습니다.

---

# 5. Output Root

Pipeline 실행 산출물 Root:

```text
outputs/
```

공통 Path 관리:

```text
config/paths.py
```

개념적인 문서별 Output 구조:

```text
outputs/
└── announcement_001/
    ├── 01_parsed/
    ├── 02_normalized/
    ├── 03_structured/
    ├── 04_chunks/
    └── 05_embeddings/
```

실제 Path 계산의 Source of Truth:

```text
config/paths.py
run_pipeline.py
```

---

# 6. Stage 1 — Parse

## 목적

HWP/HWPX 원본 문서를 Python Pipeline에서 후속 처리 가능한 JSON 구조로 변환합니다.

---

## HWP Parser

파일:

```text
pipeline/parser/hwp_parser.py
```

입력:

```text
*.hwp
```

출력 예:

```text
outputs/<announcement_id>/01_parsed/hwp.json
```

호출 구조:

```text
run_pipeline.py
    ↓
parse_hwp_file()
    ↓
pipeline/parser/hwp_parser.py
```

---

## HWPX Parser

파일:

```text
pipeline/parser/hwpx_parser.py
```

입력:

```text
*.hwpx
```

출력 예:

```text
outputs/<announcement_id>/01_parsed/hwpx.json
```

호출 구조:

```text
run_pipeline.py
    ↓
parse_hwpx_file()
    ↓
pipeline/parser/hwpx_parser.py
```

---

## Parser Common

공통 처리:

```text
pipeline/parser/common.py
```

Parser Library:

```text
pipeline/parser/libs/hwp/
pipeline/parser/libs/hwpx/
```

HWP/HWPX Parser Library 경로 및 공통 설정 문제는 이 영역을 확인합니다.

---

# 7. Parse Stage 실행

전체 프로젝트 Root에서:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage parse
```

정상 실행 시 각 공고별로 Parser 결과가 생성됩니다.

예:

```text
[HWP 파싱]
문서 ID: announcement_001
입력: tests/fixtures/documents/announcement_001/...
출력: outputs/announcement_001/01_parsed/hwp.json
```

또는:

```text
[HWPX 파싱]
...
출력: outputs/announcement_001/01_parsed/hwpx.json
```

---

# 8. Parse 결과 확인

예:

```bash
find outputs \
  -path '*/01_parsed/*' \
  -type f \
  | sort
```

특정 공고:

```bash
find outputs/announcement_001/01_parsed \
  -type f \
  | sort
```

Parser 결과가 없으면 Normalizer 이하 단계부터 수정하지 않습니다.

먼저 Parser 문제를 해결합니다.

---

# 9. Stage 2 — Normalize

## 목적

Parser 결과를 후속 Structure Pipeline에서 안정적으로 사용할 수 있도록 정규화합니다.

파일:

```text
pipeline/normalizer/document_normalizer.py
```

입력:

```text
01_parsed/*.json
```

출력:

```text
02_normalized/*.json
```

호출 구조:

```text
run_pipeline.py
    ↓
normalize_file()
    ↓
document_normalizer.py
```

---

# 10. Normalizer 주요 처리

현재 Normalizer는 다음 성격의 작업을 수행합니다.

```text
Control Character 정리
Special Character 정규화
Measurement Unit 정규화
Private Use Character 확인
Bullet Spacing 정리
Roman Numeral 처리
Paragraph 정규화
Table 정규화
Cell 정규화
Source 정보 정규화
Search Text 생성
```

즉 Parser의 원시 결과를 그대로 RAG에 사용하는 것이 아니라,
먼저 이 단계에서 표현을 통일합니다.

---

# 11. Normalize Stage 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage normalize
```

출력 예:

```text
outputs/announcement_001/02_normalized/hwp.json
outputs/announcement_001/02_normalized/hwpx.json
```

---

# 12. Normalize 결과 확인

```bash
find outputs \
  -path '*/02_normalized/*' \
  -type f \
  | sort
```

정규화 결과에서 확인할 수 있는 주요 통계 예:

```text
Section 수
문단 수
표 수
셀 수
이미지 수
실제 빈 셀 수
미정의 Block 수
미검증 PUA 문자 수
Normalizer 경고 수
```

경고가 있다고 해서 무조건 Pipeline 실패는 아닙니다.

다만 후속 검색 품질에 영향을 줄 수 있는 문자/구조 경고는 확인합니다.

---

# 13. Stage 3 — Structure

## 목적

Normalized Document를 단순 문단/표 집합이 아니라,
공고문의 논리적 구조를 가진 데이터로 변환합니다.

Runner:

```text
pipeline/structure/run_structure.py
```

입력:

```text
02_normalized/*.json
```

출력:

```text
03_structured/<format>/
```

호출:

```text
run_pipeline.py
    ↓
structure_file()
    ↓
run_structure.py
```

---

# 14. Structure 내부 단계

현재 주요 파일:

```text
pipeline/structure/
├── build_document_step1.py
├── build_domain_step2.py
├── build_table_step3.py
├── domain_rules.json
├── finalize_structure.py
├── run_structure.py
├── value_normalizer.py
└── verification.py
```

개념:

```text
Normalized Document
        ↓
build_document_step1
        ↓
build_domain_step2
        ↓
build_table_step3
        ↓
Value Normalization
        ↓
Finalize
        ↓
Verification
```

---

# 15. Structure Stage 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage structure
```

출력 예:

```text
outputs/announcement_001/03_structured/hwp/
outputs/announcement_001/03_structured/hwpx/
```

현재 후속 Chunking에서 사용되는 주요 Structured 결과 중 하나:

```text
step4-1_value_normalized.json
```

Structure 단계는 최종 검증 Report도 생성할 수 있습니다.

예:

```text
step4-3_verification.json
```

---

# 16. Structure 결과 확인

예:

```bash
find outputs/announcement_001/03_structured \
  -type f \
  | sort
```

Structure 오류가 발생하면 먼저:

```text
Normalized JSON
→ Structure JSON
```

사이에서 데이터가 어떻게 바뀌었는지 비교합니다.

Chunking부터 수정하지 않습니다.

---

# 17. Stage 4 — Chunking

## 목적

Structured Document를 Vector Search와 LLM Context에서 사용하기 적합한 검색 단위로 분할합니다.

Runner:

```text
pipeline/chunking/run_chunking.py
```

입력 예:

```text
03_structured/<format>/step4-1_value_normalized.json
```

출력:

```text
04_chunks/<format>/chunks.json
```

호출:

```text
run_pipeline.py
    ↓
chunk_file()
    ↓
run_chunking.py
```

---

# 18. Chunking 내부 구조

```text
pipeline/chunking/
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

처리 개념:

```text
Structured Document
      ↓
Intro 처리
      ↓
Section Recursive Walk
      ↓
Paragraph Chunking
      ↓
Table Chunking
      ↓
Search/Embedding Text 생성
      ↓
Validation
      ↓
chunks.json
```

---

# 19. Chunk Type

현재 실행 결과에서 확인된 Chunk 유형 예:

```text
intro
paragraph_group
table_record
table_fallback
```

각 Chunk는 문서의 내용 특성에 따라 다른 방식으로 생성됩니다.

특히 Table 정보는 단순 문자열 전체를 한 Chunk로 만들기보다
행/열 의미가 유지되는 방식으로 처리하는 것이 중요합니다.

---

# 20. Chunking Stage 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage chunk
```

로그 마지막 부분만 확인하려면:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage chunk 2>&1 | tail -120
```

---

# 21. Chunk 결과

예:

```text
outputs/announcement_001/04_chunks/hwpx/chunks.json
```

확인:

```bash
find outputs \
  -path '*/04_chunks/*/chunks.json' \
  -type f \
  | sort
```

Chunking 로그에서 확인할 항목:

```text
총 청크 수
청크 유형
최대 토큰 수
평균 토큰 수
최대 초과 청크
원본 정규화 경고
```

---

# 22. Chunk Contract

Chunking을 수정할 때는 후속 Pipeline/RAG가 필요로 하는 의미를 유지해야 합니다.

특히 다음 정보가 중요합니다.

```text
Chunk ID
Announcement relation
Document relation
Chunk Type
Section Path
Title
Content
Search Text
Source Reference
Metadata
```

정확한 Field 정의는 현재 코드:

```text
pipeline/chunking/models.py
pipeline/chunking/text_builder.py
pipeline/chunking/run_chunking.py
```

를 Source of Truth로 사용합니다.

---

# 23. Stage 5 — Embedding

## 목적

Chunk의 검색용 Text를 Dense Vector로 변환합니다.

Runner:

```text
pipeline/embedding/run_embeddings.py
```

현재 모델:

```text
BAAI/bge-m3
```

현재 확인된 Embedding Dimension:

```text
1024
```

---

# 24. Embedding 입력/출력

입력:

```text
04_chunks/<format>/chunks.json
```

출력 예:

```text
05_embeddings/<format>/
├── embeddings.npy
├── metadata.json
└── embedding_report.json
```

---

# 25. Embedding 내부 구조

```text
pipeline/embedding/
├── config.py
├── embedding_generator.py
├── input_loader.py
├── model_loader.py
├── models.py
├── output_writer.py
├── run_embeddings.py
└── validator.py
```

흐름:

```text
chunks.json
    ↓
input_loader.py
    ↓
model_loader.py
    ↓
BAAI/bge-m3
    ↓
embedding_generator.py
    ↓
validator.py
    ↓
output_writer.py
```

---

# 26. Embedding Stage 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage embed
```

로그 일부만 확인:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage embed 2>&1 | tail -120
```

---

# 27. 정상 Embedding 실행 예

현재 확인된 환경 예:

```text
모델: BAAI/bge-m3
장치: cuda:0
GPU: NVIDIA L4
Vector Dimension: 1024
L2 Normalize: True
```

결과 예:

```text
벡터 shape: (291, 1024)
벡터 차원: 1024
```

---

# 28. Embedding 결과 확인

```bash
find outputs \
  -path '*/05_embeddings/*' \
  -type f \
  | sort
```

특정 공고:

```bash
find outputs/announcement_001/05_embeddings \
  -type f \
  | sort
```

---

# 29. Document Embedding과 Query Embedding 관계

문서 Chunk Embedding:

```text
pipeline/embedding/
```

사용자 질문 Embedding:

```text
rag/retrieval/query_embedding.py
```

두 Vector는 동일한 의미 공간에서 비교되어야 합니다.

현재 Query Embedding 역시 BGE-M3 Model Loader를 재사용합니다.

연결:

```text
pipeline/embedding/model_loader.py
          ↑
          │
rag/retrieval/query_embedding.py
```

Embedding 모델 또는 Dimension을 변경할 경우 양쪽을 모두 수정해야 합니다.

---

# 30. Stage 6 — Persistence

Pipeline 산출물을 DB에 기록하는 Service:

```text
backend/app/services/pipeline_persistence.py
```

Pipeline과 DB 사이의 연결:

```text
outputs/
    ↓
pipeline_persistence.py
    ↓
ProcessingRun
DocumentStructure
ChunkSet
Chunks
Embeddings
    ↓
PostgreSQL
```

---

# 31. Persistence Dry Run

실제 DB에 쓰기 전에 검증할 수 있습니다.

예:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m backend.app.services.pipeline_persistence \
--announcement-key announcement_001
```

정상 예:

```text
PIPELINE PERSISTENCE DRY RUN

announcement_key: announcement_001
verification: pass
chunk_count: 291
model: BAAI/bge-m3
dimension: 1024
embedding_count: 291

DRY RUN: PASS
DB WRITE: NO
```

---

# 32. Persistence Write

실제 DB Write:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m backend.app.services.pipeline_persistence \
--announcement-key announcement_001 \
--write
```

정상 예:

```text
DB WRITE: PASS
ACTIVE SWITCH: NO
```

중요:

`--write`는 DB에 데이터를 저장하지만 새 Processing Run을 바로 Active로 만들지 않을 수 있습니다.

---

# 33. Processing Run Activation

Persistence 이후 서비스에서 새 데이터를 사용하려면 Processing Run을 활성화해야 할 수 있습니다.

관련 함수:

```text
activate_processing_run()
```

예:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from backend.app.services.pipeline_persistence import activate_processing_run

result = activate_processing_run(5)

for key, value in result.items():
    print(f"{key}: {value}")
PY
```

정상적인 Activation은 이전 Run을 비활성화하고 새 Run/ChunkSet을 활성화합니다.

---

# 34. Active Processing 구조

개념:

```text
Document
    ↓
ProcessingRun
    ↓
ChunkSet
    ↓
Chunks
    ↓
Embeddings
```

서비스에서는:

```text
ProcessingRun.is_active = TRUE
ChunkSet.is_active = TRUE
```

인 데이터를 검색 대상으로 사용합니다.

따라서 DB에 Chunk가 존재한다고 해서 무조건 Runtime RAG가 검색하는 것은 아닙니다.

Active 상태를 함께 확인해야 합니다.

---

# 35. DB 연결 검증

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from sqlalchemy import text
from backend.app.db.session import engine

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1")).scalar_one()

print("DB CONNECTION:", result)
PY
```

정상:

```text
DB CONNECTION: 1
```

---

# 36. Pipeline 전체 연결 구조

```text
tests/fixtures/documents/
        │
        ▼
    run_pipeline.py
        │
        ▼
┌─────────────────────┐
│ Parser              │
│ hwp_parser.py       │
│ hwpx_parser.py      │
└─────────┬───────────┘
          ▼
    01_parsed
          │
          ▼
┌─────────────────────┐
│ Normalizer          │
│ document_normalizer │
└─────────┬───────────┘
          ▼
    02_normalized
          │
          ▼
┌─────────────────────┐
│ Structure           │
│ run_structure.py    │
└─────────┬───────────┘
          ▼
    03_structured
          │
          ▼
┌─────────────────────┐
│ Chunking            │
│ run_chunking.py     │
└─────────┬───────────┘
          ▼
     04_chunks
          │
          ▼
┌─────────────────────┐
│ Embedding           │
│ run_embeddings.py   │
└─────────┬───────────┘
          ▼
   05_embeddings
          │
          ▼
┌─────────────────────┐
│ Persistence         │
│ pipeline_persistence│
└─────────┬───────────┘
          ▼
 PostgreSQL + pgvector
          │
          ▼
       Runtime RAG
```

---

# 37. Stage별 디버깅 원칙

Pipeline 문제를 발견하면 무조건 첫 단계부터 수정하지 않습니다.

먼저 처음으로 잘못된 데이터가 만들어진 Stage를 찾습니다.

```text
Original
 ↓
Parsed
 ↓
Normalized
 ↓
Structured
 ↓
Chunks
 ↓
Embedding
 ↓
DB
```

---

## Parsed가 잘못됨

확인:

```text
pipeline/parser/
```

---

## Parsed 정상, Normalized가 잘못됨

확인:

```text
pipeline/normalizer/
```

---

## Normalized 정상, Structured가 잘못됨

확인:

```text
pipeline/structure/
```

---

## Structured 정상, Chunk가 잘못됨

확인:

```text
pipeline/chunking/
```

---

## Chunk 정상, Vector가 잘못됨

확인:

```text
pipeline/embedding/
```

---

## Output 정상, DB가 잘못됨

확인:

```text
backend/app/services/pipeline_persistence.py
backend/app/models/
backend/app/db/
```

---

# 38. Parser 변경 시 영향 범위

Parser를 새 구현으로 교체할 경우 가장 중요한 것은:

```text
Parser → Normalizer Contract
```

입니다.

가능하면 다음은 유지합니다.

```text
Document metadata
Section data
Paragraph data
Table data
Cell data
Source information
```

이 계약을 유지하면:

```text
Normalizer
Structure
Chunking
Embedding
Persistence
RAG
```

전체를 다시 작성하지 않아도 됩니다.

---

# 39. Structure 변경 시 영향 범위

Structure가 만드는 Section/Table 의미가 변경되면:

```text
Chunking
RAG Search Text
Generation Context
```

까지 영향을 받을 수 있습니다.

따라서 Structure Schema 변경 전:

```text
pipeline/chunking/
```

이 어떤 필드를 사용하는지 확인해야 합니다.

---

# 40. Chunking 변경 시 영향 범위

Chunking은 Runtime RAG 품질에 직접적인 영향을 줍니다.

특히 다음 값의 의미를 유지합니다.

```text
chunk ID
content
search text
section path
title
source
document relation
announcement relation
```

Chunk Schema를 변경하면 확인:

```text
pipeline/embedding/
backend/app/services/pipeline_persistence.py
backend/app/models/chunk.py
rag/db_pipeline.py
rag/generation/context_builder.py
```

---

# 41. Embedding 변경 시 영향 범위

Embedding Model을 변경하면 최소 다음을 확인합니다.

```text
pipeline/embedding/
rag/retrieval/query_embedding.py
rag/db_pipeline.py
backend/app/models/embedding.py
migrations/
```

특히 Dimension이 변경되면 pgvector Column 정의도 변경해야 할 수 있습니다.

현재 확인된 Dimension:

```text
1024
```

---

# 42. Pipeline Output을 삭제해도 되는가

`outputs/`는 Source Code는 아닙니다.

하지만 현재 개발/검증 과정에서는 다음 목적으로 사용됩니다.

```text
Pipeline Stage 검증
Persistence 입력
문제 발생 Stage 비교
```

따라서 개발 중에는 무조건 삭제하지 않습니다.

완전히 재생성할 수 있다는 것이 확인되고,
DB Persistence까지 완료된 이후 필요에 따라 정리합니다.

---

# 43. 새로운 공고 문서를 수동으로 추가할 경우

현재 Fixture 기반 검증 흐름에서는 개념적으로:

```text
tests/fixtures/documents/
└── announcement_XXX/
    ├── document.hwp
    └── document.hwpx
```

형태로 추가합니다.

이후:

```bash
python run_pipeline.py --stage parse
python run_pipeline.py --stage normalize
python run_pipeline.py --stage structure
python run_pipeline.py --stage chunk
python run_pipeline.py --stage embed
```

순으로 실행하여 각 Stage 결과를 확인할 수 있습니다.

단 실제 운영 Crawler가 구현되면 원본 파일 입력 방식은 변경될 수 있습니다.

---

# 44. Pipeline과 Crawler의 경계

현재:

```text
crawler/
└── __init__.py
```

만 존재하고 실제 수집 기능은 미구현입니다.

따라서 현재 Pipeline은 Crawler에 의존해서 실행되는 구조가 아닙니다.

향후 권장 경계:

```text
Crawler
   ↓
Original Document
   ↓
Pipeline
```

Crawler는 문서를 가져오는 책임까지만 담당하고,
문서 내부 해석은 Pipeline이 담당하는 구조를 유지하는 것이 좋습니다.

---

# 45. 전체 Pipeline 검증 Checklist

문서를 하나 처리한 뒤 다음 항목을 순서대로 확인합니다.

```text
[ ] 원본 HWP/HWPX 존재
[ ] Parsed JSON 생성
[ ] Normalized JSON 생성
[ ] Structured 결과 생성
[ ] Structure verification 확인
[ ] chunks.json 생성
[ ] Chunk count 정상
[ ] Embedding 생성
[ ] Embedding dimension 정상
[ ] Embedding count == Chunk count
[ ] Persistence dry-run PASS
[ ] DB WRITE PASS
[ ] Processing Run 활성화
[ ] Active ChunkSet 확인
[ ] Runtime Retrieval 결과 확인
```

---

# 46. AI가 Pipeline을 수정할 때 반드시 확인할 것

AI에게 Pipeline 수정 작업을 맡기는 경우 최소 다음 파일을 전달합니다.

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/PIPELINE.md
run_pipeline.py
config/paths.py
pipeline/
```

DB Persistence 문제까지 포함되면 추가:

```text
backend/app/services/pipeline_persistence.py
backend/app/models/
```

AI는 수정 전에 다음 질문에 답할 수 있어야 합니다.

```text
1. 어느 Stage가 문제인가?
2. 해당 Stage 입력은 무엇인가?
3. 출력은 무엇인가?
4. 누가 이 Stage를 호출하는가?
5. 다음 Stage는 어떤 Field를 사용하는가?
6. Schema를 변경해야 하는가?
7. Schema를 유지한 채 내부 구현만 바꿀 수 있는가?
```

---

# 47. Pipeline Source of Truth

| 항목 | Source of Truth |
|---|---|
| 전체 Stage 순서 | `run_pipeline.py` |
| Path | `config/paths.py` |
| HWP Parsing | `pipeline/parser/hwp_parser.py` |
| HWPX Parsing | `pipeline/parser/hwpx_parser.py` |
| Normalization | `pipeline/normalizer/document_normalizer.py` |
| Structure | `pipeline/structure/run_structure.py` |
| Chunking | `pipeline/chunking/run_chunking.py` |
| Embedding | `pipeline/embedding/run_embeddings.py` |
| Embedding Model | `pipeline/embedding/model_loader.py` |
| Persistence | `backend/app/services/pipeline_persistence.py` |
| DB Model | `backend/app/models/` |
| DB Schema History | `migrations/` |

---

# 48. 핵심 요약

DDOKBOT의 Pipeline은 다음 한 줄로 이해할 수 있습니다.

```text
HWP/HWPX
→ Parsed JSON
→ Normalized JSON
→ Structured Document
→ Search Chunks
→ BGE-M3 Embeddings
→ PostgreSQL + pgvector
```

실제 전체 실행 제어:

```text
run_pipeline.py
```

Runtime RAG가 사용하는 데이터가 이상하다면,
먼저 Pipeline의 각 Stage 산출물을 역순으로 추측하지 말고
**처음 잘못된 결과가 만들어지는 Stage를 정확히 찾은 뒤 그 Stage만 수정합니다.**
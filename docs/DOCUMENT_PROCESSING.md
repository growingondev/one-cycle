# DDOKBOT 문서처리 파트

> 이 문서는 DDOKBOT 프로젝트를 처음 보는 개발자가 HWP/HWPX 문서처리 영역의 목적, 실행 흐름, 다른 파트와의 연결 관계, 주요 코드와 데이터 흐름을 이해하고 이어서 개발할 수 있도록 정리한 문서입니다.
>
> 기준 코드: 2026-08-27 업로드된 최신 코드

---

# 1. 담당 파트 개요

## 1.1 담당 기능

문서처리 파트는 LH 청약 공고의 HWP/HWPX 원본 파일을 RAG에서 검색하고 답변 생성에 사용할 수 있는 구조로 변환하는 역할을 담당합니다.

핵심 담당 범위는 다음과 같습니다.

```text
HWP / HWPX 원본
    ↓
실제 문서 형식 판별
    ↓
Parsing
    ↓
Normalization
    ↓
Structuring + Verification
    ↓
Chunking
    ↓
Embedding
    ↓
DB Persistence
    ↓
핵심정보 추출
    ↓
ProcessingRun 활성화
```

이 중 문서처리의 핵심 구현 영역은 다음입니다.

- HWP/HWPX 실제 내부 형식 판별
- 문단/표/중첩 표 추출
- 깨진 문자 및 PUA 문자 보정
- 제목 계층과 Section 구조화
- 표 Header-Value 관계 구조화
- 구조화 결과 검증
- 핵심정보 추출
- 전체 Pipeline 단계 연결

Chunking, Embedding, DB 자체 구현은 별도 모듈이지만 `pipeline/document_processor.py`가 전체 처리 순서를 오케스트레이션하므로 문서처리 파트에서는 입출력 계약과 실패 조건을 이해해야 합니다.

## 1.2 왜 필요한가

RAG는 원본 HWP/HWPX 파일을 직접 검색하지 않습니다.

원본 공고문에는 다음과 같은 문제가 있습니다.

- HWP/HWPX가 서로 다른 내부 구조를 가짐
- 표에 핵심 정보가 많이 포함됨
- 병합 셀과 중첩 표가 존재함
- 문서의 제목 계층이 단순 텍스트로만 추출하면 손실됨
- HWP 계열 문서에서 PUA 문자나 번호 문자가 깨질 수 있음
- 날짜, 금액, 면적, 전화번호 등 검색에 중요한 값의 표현이 다양함

따라서 문서처리 단계에서 **텍스트만 추출하는 것이 아니라 원문의 정보 관계를 최대한 유지하는 것**이 중요합니다.

문서처리 품질이 낮으면 이후 단계에서 다음 문제가 발생합니다.

```text
문서 구조 손실
→ 잘못된 Chunk 생성
→ 검색 근거 누락
→ RAG 오답 또는 답변 불가
```

즉 문서처리는 RAG의 입력 데이터 품질을 결정하는 전처리 계층입니다.

## 1.3 전체 서비스에서의 위치

```text
Crawler / 평가 문서 등록
        ↓
PostgreSQL Document 등록
        ↓
[문서처리 파트]
Format Detection
→ Parser
→ Normalizer
→ Structure
→ Chunking
→ Embedding
→ Persistence
→ Key Information
        ↓
PostgreSQL + pgvector
        ↓
RAG Retrieval
        ↓
LLM Generation
        ↓
Backend API
        ↓
Frontend
```

문서처리는 사용자 질문이 들어올 때마다 실행되는 Runtime 기능이 아닙니다.

공고문이 신규 등록되거나 문서를 재처리할 때 실행되는 **Ingestion Pipeline**입니다.

## 1.4 현재 구현 범위

현재 최신 코드에서는 다음까지 구현되어 있습니다.

- HWP/HWPX 내부 형식 자동 판별
- HWP Parser
- HWPX Parser
- 문단/표/중첩 표 추출
- Parser 공통 출력 구조
- PUA 번호 및 특수 문자 관련 보정
- Normalization
- 제목 계층 기반 문서 구조화
- Domain 분류
- 표 Header-Value 구조화
- 값 정규화 및 Verification
- Chunking 단계 연결
- BGE-M3 Embedding 단계 연결
- Pipeline 결과 DB 적재
- 핵심정보 추출 및 저장
- 실패한 ProcessingRun 비활성 유지
- 전체 성공 시 ProcessingRun 활성화
- Backend 관리자 문서 재처리 기능과 연결

---

# 2. 담당 폴더 구조

주요 폴더는 다음과 같습니다.

```text
pipeline/
├── document_processor.py
├── key_information_extractor.py
│
├── parser/
│   ├── common.py
│   ├── format_detector.py
│   ├── hwp_parser.py
│   ├── hwpx_parser.py
│   └── libs/
│       ├── hwp/hwplib-1.1.10.jar
│       └── hwpx/hwpxlib-1.0.8.jar
│
├── normalizer/
│   └── document_normalizer.py
│
├── structure/
│   ├── run_structure.py
│   ├── build_document_step1.py
│   ├── build_domain_step2.py
│   ├── build_table_step3.py
│   ├── domain_rules.json
│   ├── value_normalizer.py
│   ├── finalize_structure.py
│   └── verification.py
│
├── chunking/
│   └── ...
│
└── embedding/
    └── ...
```

연결되는 Backend 코드는 다음입니다.

```text
backend/app/services/
├── pipeline_gateway.py
├── integration_service.py
├── pipeline_persistence.py
└── key_information_service.py
```

---

# 3. 문서처리 시작 지점

문서처리는 크게 두 경로에서 시작될 수 있습니다.

## 3.1 실제 서비스/관리자 재처리

관리자가 문서 재처리를 요청하면 다음 흐름으로 실행됩니다.

```text
HTTP POST
/admin/.../documents/{document_id}/reprocess
        ↓
backend/app/api/routes/admin.py
run_document_reprocess()
        ↓ Python import
backend/app/services/pipeline_gateway.py
reprocess_document()
        ↓ 환경변수 기반 Python import
DOCUMENT_REPROCESSOR
        ↓
pipeline.document_processor:reprocess_document
        ↓
pipeline/document_processor.py
process_document()
```

`.env.example`의 현재 설정은 다음입니다.

```text
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document
```

즉 Backend와 Pipeline은 현재 별도 HTTP 서비스로 분리되어 있지 않고 **같은 Python 프로세스/코드베이스에서 import 방식으로 연결**됩니다.

## 3.2 Crawler/Integration 처리

Crawler가 공고와 Document를 DB에 등록한 뒤 Backend Integration 계층에서 문서 ID를 Pipeline으로 전달할 수 있습니다.

```text
Crawler 결과
    ↓
persist_collection_result()
    ↓
Document DB 저장
    ↓
backend/app/services/integration_service.py
process_document_ids()
    ↓
pipeline_gateway.reprocess_document()
    ↓
pipeline.document_processor.reprocess_document()
```

---

# 4. 전체 동작 흐름

`pipeline/document_processor.py`의 `process_document(document_id)`가 실제 서비스용 전체 문서처리 흐름의 핵심입니다.

현재 순서는 다음과 같습니다.

```text
1. DB Document Context 조회
2. 원본 파일 경로 확인
3. 실제 내부 형식 판별
4. Parser
5. Normalizer
6. Structure + Verification
7. Chunking
8. Embedding
9. Persistence
10. 핵심정보 추출
11. 핵심정보 DB 저장
12. ProcessingRun 활성화
```

보다 구체적으로는 다음과 같습니다.

```text
document_id
    ↓
get_registered_document_context()
    ↓
storage_path / announcement_id / filename / format
    ↓
detect_actual_document_format()
    ↓
HWP 또는 HWPX Parser 선택
    ↓
01_parsed/*.json
    ↓
document_normalizer.py
    ↓
02_normalized/*.json
    ↓
run_structure.py
    ↓
03_structured/<format>/step4-1_value_normalized.json
03_structured/<format>/step4-3_verification.json
    ↓
run_chunking.py
    ↓
04_chunks/<format>/chunks.json
    ↓
run_embeddings.py
    ↓
05_embeddings/<format>/metadata.json
05_embeddings/<format>/embeddings.npy
    ↓
persist_document_outputs()
    ↓
ProcessingRun + Structure + Chunk + Embedding DB 저장
    ↓
extract_key_information()
    ↓
upsert_key_information()
    ↓
activate_processing_run()
```

---

# 5. Stage별 주요 파일과 역할

## 5.1 실제 문서 형식 판별

### 파일

```text
pipeline/parser/format_detector.py
```

### 핵심 함수

```python
detect_actual_document_format(path)
```

### 입력

원본 HWP/HWPX 파일 경로

### 처리

파일 확장자만 신뢰하지 않고 파일 내부 시그니처/구조를 기준으로 실제 HWP 또는 HWPX 형식을 판별합니다.

### 출력

```text
"hwp"
"hwpx"
```

### 호출자

```text
pipeline/document_processor.py
process_document()
```

### 중요한 이유

실제 파일 형식과 확장자가 다른 경우 잘못된 Parser가 실행되는 문제를 방지합니다.

현재 `process_document()`는 DB에 저장된 `format`과 실제 판별 결과가 다르면 오류를 발생시키도록 되어 있습니다.

---

# 5.2 Parser 공통 코드

### 파일

```text
pipeline/parser/common.py
```

### 역할

HWP/HWPX Parser가 공통으로 사용하는 기능을 제공합니다.

주요 기능:

- Parser 예외 클래스
- JAR 경로 검증
- JVM 초기화
- 원본 문서 경로 검증
- JSON 저장/로드
- Parser 출력 경로 결정
- Parser 공통 문서 Header 생성

### 주요 요소

```text
ParserError
JarResolutionError
ParseContext
resolve_jar_path()
ensure_jvm()
validate_document_path()
build_document_header()
```

Parser 자체의 형식별 로직은 HWP/HWPX 파일에 분리되어 있고, 공통 실행 기반은 이 파일에 모여 있습니다.

---

# 5.3 HWP Parser

### 파일

```text
pipeline/parser/hwp_parser.py
```

### 핵심 진입 함수

```python
parse_hwp(...)
```

### 입력

```text
*.hwp
```

### 주요 처리

- hwplib JAR 사용
- HWP 문단 추출
- 표 추출
- 셀 내부 문단 추출
- 중첩 표 탐색
- 병합 관련 셀 정보 유지
- 문단 번호/특수 문자 복구 보조
- PUA 번호 문자 복원

### 출력

Parsed JSON

예:

```text
outputs/<announcement_key>/document_<id>/01_parsed/hwp.json
```

### 호출자

```text
pipeline/document_processor.py
_run_parser()
```

---

# 5.4 HWPX Parser

### 파일

```text
pipeline/parser/hwpx_parser.py
```

### 핵심 진입 함수

```python
parse_hwpx(...)
```

### 입력

```text
*.hwpx
```

### 주요 처리

- hwpxlib JAR 사용
- HWPX 문단/Run/Text 추출
- XML 원문을 이용한 텍스트 보정
- 표와 셀 추출
- 중첩 표 추출
- PUA 번호 문자 복원
- Library 결과와 XML 결과 차이 보완

### 출력

```text
01_parsed/hwpx.json
```

### 호출자

```text
pipeline/document_processor.py
_run_parser()
```

---

# 5.5 Normalizer

### 파일

```text
pipeline/normalizer/document_normalizer.py
```

### 목적

Parser가 추출한 원문 구조를 유지하면서 검색과 구조화에 방해가 되는 문자/표현을 정리합니다.

Parser와 Normalizer를 분리한 이유는 다음과 같습니다.

```text
Parser
= 원문에서 무엇이 추출되었는지 최대한 보존

Normalizer
= 후속 처리에 사용할 수 있도록 안전하게 보정
```

즉 Parser 단계에서 원문을 과도하게 변경하지 않는 것이 기본 원칙입니다.

### 입력

```text
01_parsed/<format>.json
```

### 출력

```text
02_normalized/<format>.json
```

### 호출자

```text
pipeline/document_processor.py
_run_normalizer()
```

---

# 5.6 Structure

Structure 단계는 하나의 파일이 아니라 여러 단계로 분리되어 있습니다.

```text
pipeline/structure/run_structure.py
        ↓
build_document_step1.py
        ↓
build_domain_step2.py
        ↓
build_table_step3.py
        ↓
value_normalizer.py
        ↓
verification.py / finalize_structure.py
```

## `build_document_step1.py`

문서의 문단과 제목을 기반으로 기본 Section 계층을 만듭니다.

주요 목적:

- 제목 후보 판별
- 번호 체계 인식
- 제목 깊이/계층 계산
- 본문을 적절한 Section에 배치

## `build_domain_step2.py`

Section 제목과 내용에 규칙을 적용해 Domain 정보를 부여합니다.

규칙 데이터:

```text
pipeline/structure/domain_rules.json
```

현재 Domain 분류는 LLM이 판단하는 방식이 아니라 **규칙 기반 분류**입니다.

## `build_table_step3.py`

표 구조를 분석합니다.

주요 기능:

- Header 탐지
- Header path 구성
- 행/열 관계 분석
- 병합 셀 처리
- 표 값을 Header와 연결
- 중첩 표 재귀 처리
- 구조화된 표 레코드 생성

문서처리 품질에서 특히 중요한 파일입니다. LH 공고문은 자격, 공급 세대, 임대조건 등 핵심 정보가 표에 많이 포함되기 때문입니다.

## `value_normalizer.py`

구조화된 값에서 검색에 중요한 Entity와 정규화 정보를 만듭니다.

현재 코드에서 다루는 주요 값:

- 날짜
- 시간
- 금액
- 면적
- 전화번호
- 비율
- PUA 문자 검사

## `verification.py`

구조화 결과가 다음 단계로 전달 가능한 상태인지 검증합니다.

`pipeline_persistence.py`에서는 최종 verification 상태가 `pass`인지 확인한 뒤 DB 적재를 진행합니다.

---


# 5.7 문서처리 내부 규칙을 이해할 때 먼저 알아야 할 것

이 절은 개별 코드를 수정하기 전에 알아야 하는 구현 원칙과 탐색 기준을 정리합니다. 문서처리는 단순 텍스트 추출기가 아니라 **원문에 존재하는 위치·계층·표 관계를 후속 RAG 단계에서 사용할 수 있도록 보존하는 계층**입니다.

## 5.7.1 Parser에서는 가능한 한 원문 구조를 보존한다

Parser의 기본 원칙은 다음과 같습니다.

```text
원본에서 읽은 문단/표/셀 구조
        ↓
최대한 그대로 Parsed JSON에 기록
        ↓
검색 편의를 위한 보정은 Normalizer 이후 단계에서 수행
```

따라서 Parser를 수정할 때는 단순히 화면에 보이는 문자열만 맞추기보다 다음 정보가 유지되는지 함께 확인해야 합니다.

- 문단 순서
- 표 위치
- 셀의 `row`, `col`
- `row_span`, `col_span`
- 셀 안의 문단
- 셀 안의 중첩 표
- 원본 위치를 추적할 수 있는 `source`
- 중첩 위치를 추적할 수 있는 `object_path`

이 정보를 제거하면 Structure 단계에서 Header-Value 관계나 중첩 표의 부모 관계를 복구하기 어려워질 수 있습니다.

## 5.7.2 HWP와 HWPX는 같은 결과를 목표로 하지만 탐색 방식이 다르다

최종 Parsed JSON의 목적은 같지만 원본 라이브러리 구조가 다르므로 표와 중첩 표를 찾는 방식도 다릅니다.

### HWP

HWP 셀 내부 중첩 표 탐색 함수:

```python
find_nested_tables_in_hwp_cell(...)
```

파일:

```text
pipeline/parser/hwp_parser.py
```

핵심 탐색 순서는 다음과 같습니다.

```text
Cell
 ↓
cell.getParagraphList()
 ↓
Paragraph
 ↓
paragraph.getControlList()
 ↓
Control
 ↓
Control의 Java class가 HWP Table인지 확인
 ↓
parse_table() 재귀 호출
```

즉 HWP에서는 **셀 안의 각 문단이 가진 Control 목록**에서 표 Control을 찾습니다.

표가 발견되면 `source`에 다음과 같은 부모 위치 정보가 기록됩니다.

```text
location = nested_table
parent_table_index
parent_cell
nested_depth
object_path
```

그리고 다시 `parse_table()`을 호출하기 때문에 중첩 표 안에 또 다른 표가 있는 경우에도 같은 방식으로 내려갈 수 있습니다.

무한 재귀나 비정상 문서를 막기 위해 `ParseContext.max_nested_depth`를 확인하며 최대 깊이에 도달하면 경고를 남기고 탐색을 중단합니다.

### HWPX

HWPX 셀 내부 중첩 표 탐색 함수:

```python
find_nested_tables_in_hwpx_cell(...)
```

파일:

```text
pipeline/parser/hwpx_parser.py
```

핵심 탐색 순서는 다음과 같습니다.

```text
Cell
 ↓
cell.subList()
 ↓
Paragraph
 ↓
Run
 ↓
RunItem
 ↓
RunItem의 Java class가 HWPX Table인지 확인
 ↓
parse_table() 재귀 호출
```

HWPX는 HWP와 달리 `Paragraph → Run → RunItem` 구조를 내려가면서 Table 객체를 찾습니다.

따라서 **HWP 중첩 표 수정 코드를 HWPX에 그대로 복사하면 안 됩니다.** 공통 출력 형태는 맞추되 원본 탐색 방식은 각 Parser에서 따로 유지해야 합니다.

## 5.7.3 중첩 표는 Parser에서 찾고 Structure에서 다시 독립적으로 분석한다

중첩 표 처리는 Parser에서 끝나지 않습니다.

Structure 단계의 핵심 함수:

```python
iter_tables_recursive(source)
```

파일:

```text
pipeline/structure/build_table_step3.py
```

이 함수는 다음 위치의 표를 재귀적으로 순회합니다.

```text
문서 intro
Section contents
Table
 └─ Cell
     └─ blocks
         └─ Nested Table
```

표를 발견하면 해당 표를 하나의 분석 대상으로 넘기고, 그 표의 각 셀 `blocks` 안으로 다시 들어가 하위 표를 찾습니다.

이때 `nested_depth`를 증가시키므로 최종 분석 결과에서 최상위 표와 중첩 표를 구분할 수 있습니다.

따라서 중첩 표 문제를 디버깅할 때는 반드시 두 단계를 나누어 확인합니다.

```text
1. 01_parsed에서 중첩 표 자체가 추출되었는가?
2. 03_structured에서 그 중첩 표가 독립적으로 구조화되었는가?
```

1번부터 없다면 Parser 문제이고, 1번에는 존재하지만 2번에서 사라졌다면 Structure 문제로 볼 수 있습니다.

## 5.7.4 병합 셀은 `row_span`, `col_span`을 기준으로 해석한다

표 셀은 단순한 `(row, col)` 값만 보는 것이 아니라 병합 범위까지 함께 사용합니다.

관련 파일:

```text
pipeline/structure/build_table_step3.py
```

중요한 함수:

```python
cell_range()
build_grid()
build_merged_value()
build_row_record()
```

현재 구조화 정책의 핵심은 다음과 같습니다.

- 세로 병합 `row_span` 값은 필요한 데이터 행에 상속
- 가로 병합 `col_span > 1` 데이터 셀은 각 열에 같은 값을 무조건 반복 저장하지 않음
- 가로 병합 값은 `record.merged_values`에 한 번 저장
- Header는 병합 범위를 고려해 경로를 계산

따라서 표 오류를 확인할 때 셀의 `text`만 보면 안 되고 반드시 아래를 같이 확인해야 합니다.

```text
row
col
row_span
col_span
header_path
merged_values
```

## 5.7.5 제목은 단순한 정규식 하나로 결정하지 않는다

파일:

```text
pipeline/structure/build_document_step1.py
```

대표 함수:

```python
parse_marker()
parse_standalone_marker()
semantic_heading_candidate()
paragraph_heading_candidate()
infer_heading_scheme()
assign_levels()
build_hierarchy()
```

현재 인식하는 대표 번호 패턴은 다음과 같습니다.

```text
제1장 / 제2편 등 chapter
Ⅰ. / Ⅱ. 등 roman
1.1 / 1.2 등 decimal
1. / 2. 등 arabic_dot
(1) / (2) 등 arabic_paren
1) / 2) 등 arabic_rparen
① / ② 등 circled
가. / 나. 등 korean_dot
```

번호가 없는 제목도 일부 보조 규칙으로 판별합니다. 다만 일반 본문을 제목으로 잘못 인식하지 않도록 보수적으로 처리합니다.

또한 `infer_heading_scheme()`에서 **문서 전체에서 반복되는 marker 패턴을 보고 제목 레벨을 추론**한 뒤 `assign_levels()`와 `build_hierarchy()`가 실제 Section 계층을 만듭니다.

따라서 특정 제목 하나가 잘못 분류됐다고 해서 정규식만 바로 수정하기보다 다음 순서로 확인하는 것이 좋습니다.

```text
parse_marker()에서 marker 자체가 잡히는가?
        ↓
heading candidate로 선정되는가?
        ↓
infer_heading_scheme() 결과가 어떻게 나왔는가?
        ↓
assign_levels()에서 어떤 level을 받았는가?
        ↓
build_hierarchy()에서 어느 Section 밑에 들어갔는가?
```

## 5.7.6 Domain 분류는 현재 규칙 기반이다

파일:

```text
pipeline/structure/build_domain_step2.py
pipeline/structure/domain_rules.json
```

Section 제목과 내용에서 규칙에 해당하는 표현을 찾아 Domain을 부여합니다.

새로운 공고문에서 Domain이 잘못 붙는 경우 먼저 `domain_rules.json`에 해당 표현이 존재하는지 확인합니다. 현재 단계에서는 LLM이 Section 의미를 자유롭게 판단하여 분류하는 구조가 아닙니다.

## 5.7.7 Normalizer를 수정할 때 원본 필드와 검색용 필드를 구분한다

관련 함수:

```python
normalize_text()
normalize_content_text()
build_search_text()
normalize_paragraph()
normalize_cell()
normalize_table()
```

Normalizer는 제어 문자, 특수 문자, 단위 표현, PUA 등을 정리하고 검색에 사용할 `search_text`를 생성합니다.

문자 보정 규칙을 추가할 때는 **원본 의미가 바뀌지 않는지**, 그리고 Paragraph뿐 아니라 Cell/Table 내부에도 동일한 정규화가 적용되는지 확인해야 합니다.

---

# 5.8 주요 코드를 빠르게 찾는 방법

프로젝트를 처음 인수받은 개발자는 파일 전체를 처음부터 읽기보다 **진입 함수 → 호출 함수 → 출력 JSON** 순으로 따라가는 것이 빠릅니다.

## 전체 Pipeline 진입점 찾기

```bash
grep -Rni "def process_document\|def reprocess_document" pipeline backend/app
```

먼저 다음 파일을 찾습니다.

```text
pipeline/document_processor.py
```

그 후 `_run_parser`, `_run_normalizer`, `_run_structure` 등 실제 Stage 실행 함수를 따라갑니다.

## Parser의 표 처리 찾기

```bash
grep -n "def parse_table" pipeline/parser/hwp_parser.py
grep -n "def parse_table" pipeline/parser/hwpx_parser.py
```

## 중첩 표 처리 찾기

```bash
grep -Rni "nested_table\|find_nested_tables\|nested_depth" pipeline/parser pipeline/structure
```

주요 확인 함수:

```text
hwp_parser.py
  find_nested_tables_in_hwp_cell()
  parse_table()

hwpx_parser.py
  find_nested_tables_in_hwpx_cell()
  parse_table()

build_table_step3.py
  iter_tables_recursive()
```

## 병합 셀 처리 찾기

```bash
grep -Rni "row_span\|col_span\|merged_values" pipeline/parser pipeline/normalizer pipeline/structure
```

## 제목 판별 로직 찾기

```bash
grep -n "MARKER_PATTERNS\|def parse_marker\|def infer_heading_scheme\|def assign_levels" \
  pipeline/structure/build_document_step1.py
```

## Domain 규칙 찾기

```bash
grep -Rni "domain_rules" pipeline/structure
```

실제 규칙 수정은 다음 파일을 확인합니다.

```text
pipeline/structure/domain_rules.json
```

## PUA/깨진 문자 처리 찾기

```bash
grep -Rni "PUA\|private_use\|replace_pua" pipeline/parser pipeline/normalizer pipeline/structure
```

## 핵심정보 추출 로직 찾기

```bash
grep -n "^def " pipeline/key_information_extractor.py
```

특정 필드의 추출 문제가 발생했다면 필드명을 직접 검색하는 것도 가장 빠릅니다.

```bash
grep -n "application_period\|winner_announcement\|contact_information" \
  pipeline/key_information_extractor.py
```

---

# 5.9 출력 JSON으로 문제 발생 Stage 찾는 방법

문서처리 문제는 최종 DB만 보고 원인을 찾기보다 **Stage별 산출물을 앞에서부터 비교**하는 것이 가장 빠릅니다.

```text
원본 문서
 ↓
01_parsed
 ↓
02_normalized
 ↓
03_structured
 ↓
04_chunks
 ↓
05_embeddings
 ↓
DB
```

예를 들어 최종 RAG에서 특정 표 값이 검색되지 않는다면 다음 순서로 확인합니다.

### 1단계 — Parsed JSON

확인할 것:

- 해당 텍스트가 추출되었는가?
- 해당 표가 존재하는가?
- 셀 위치가 맞는가?
- `row_span`, `col_span`이 보존됐는가?
- 중첩 표가 존재하는가?

여기서 문제가 있으면 **Parser**를 확인합니다.

### 2단계 — Normalized JSON

확인할 것:

- 원문 텍스트가 정규화 과정에서 사라지거나 변형되지 않았는가?
- PUA/특수문자가 기대한 값으로 보정됐는가?
- `search_text`가 정상 생성됐는가?

여기서 처음 문제가 발생하면 **Normalizer**를 확인합니다.

### 3단계 — Structured JSON

확인할 것:

- 올바른 Section에 포함됐는가?
- 제목 계층이 맞는가?
- Domain이 맞는가?
- 표 Header와 Value가 올바르게 연결됐는가?
- 병합 값이 `merged_values` 등에 보존됐는가?
- 중첩 표가 독립적인 분석 대상으로 남아 있는가?

여기서 처음 문제가 발생하면 **Structure**를 확인합니다.

### 4단계 — chunks.json

Structured JSON에는 정보가 있는데 검색되지 않는다면 청크를 확인합니다.

- 필요한 정보가 청크에 포함됐는가?
- Header와 Value가 같은 청크에 유지됐는가?
- 청크 분할 때문에 정보 관계가 끊기지 않았는가?

이 경우 **Chunking** 문제일 가능성이 높습니다.

### 5단계 — DB / Retrieval

청크에도 정보가 존재한다면 DB 적재와 Retrieval을 확인합니다.

이 방식으로 보면 다음과 같이 책임 Stage를 빠르게 좁힐 수 있습니다.

```text
원문에 있음 + Parsed에 없음       → Parser
Parsed에 있음 + Normalized에 없음 → Normalizer
Normalized에 있음 + Structure 오류 → Structure
Structure 정상 + Chunk에 없음      → Chunking
Chunk 정상 + 검색 결과에 없음      → Retrieval/Embedding/DB
검색 근거 정상 + 답변 오류          → Generation/Prompt
```

---

# 5.10 문서처리 코드를 수정할 때의 기본 점검 사항

문서처리 코드는 앞 단계 Schema가 뒤 단계의 입력이 되기 때문에 한 파일만 보고 수정하면 안 됩니다.

수정 전 최소한 다음을 확인합니다.

```text
[Parser 변경]
Parser → Normalizer → Structure → Chunking

[Normalizer 변경]
Normalizer → Structure → Chunking

[Structure 변경]
Structure → Chunking → Persistence → Key Information

[Chunk Schema 변경]
Chunking → Embedding → Persistence → Retrieval
```

특히 필드명을 변경하거나 삭제하는 경우 저장하는 쪽과 읽는 쪽을 함께 검색합니다.

예:

```bash
grep -Rni '"row_span"\|\.get("row_span")' pipeline backend rag
```

새 공고문을 적용했을 때는 한 문서가 성공했다는 것만 확인하지 말고 다음 관점으로 보는 것이 좋습니다.

- 일반 문단 중심 문서
- 표가 많은 문서
- 병합 셀이 많은 문서
- 중첩 표가 있는 문서
- 번호 없는 제목이 있는 문서
- PUA/특수문자가 포함된 문서
- 날짜 범위나 금액 표현이 다양한 문서

목표는 모든 문서 형식을 완벽하게 일반화하는 것이 아니라, **RAG가 답변에 필요한 정보 관계가 문서처리 과정에서 손실되지 않도록 안정성을 높이는 것**입니다.

---

# 6. 출력 파일 구조

서비스 Pipeline의 기본 출력 위치는 `config/paths.py`의 `OUTPUT_ROOT`를 기준으로 합니다.

문서 한 건의 개념적인 구조는 다음과 같습니다.

```text
outputs/
└── <announcement_key>/
    └── document_<document_id>/
        ├── 01_parsed/
        │   └── <format>.json
        │
        ├── 02_normalized/
        │   └── <format>.json
        │
        ├── 03_structured/
        │   └── <format>/
        │       ├── step1-*.json
        │       ├── step2-*.json
        │       ├── step3-*.json
        │       ├── step4-1_value_normalized.json
        │       └── step4-3_verification.json
        │
        ├── 04_chunks/
        │   └── <format>/chunks.json
        │
        └── 05_embeddings/
            └── <format>/
                ├── metadata.json
                └── embeddings.npy
```

이 파일들은 단순 Debug 산출물이 아니라 DB Persistence의 입력으로도 사용됩니다.

---

# 7. Chunking/Embedding과의 연결

문서처리 파트의 구조화 결과는 바로 RAG가 읽는 것이 아니라 Chunking과 Embedding을 거칩니다.

## 연결 방식

**Python subprocess + 파일**

`pipeline/document_processor.py`는 각 실행 파일을 하위 Python 프로세스로 실행합니다.

```text
Structure JSON
    ↓ 파일
pipeline/chunking/run_chunking.py
    ↓
chunks.json
    ↓ 파일
pipeline/embedding/run_embeddings.py
    ↓
metadata.json + embeddings.npy
```

따라서 Structure JSON의 Schema를 변경할 경우 Chunking 코드에 미치는 영향을 반드시 확인해야 합니다.

---

# 8. DB와의 연결

문서처리는 DB와 두 시점에서 연결됩니다.

## 8.1 시작 시 Document Context 조회

```text
pipeline/document_processor.py
    ↓ Python import
backend/app/services/pipeline_persistence.py
    ↓ DB
PostgreSQL
```

호출 함수:

```python
get_registered_document_context(document_id)
```

받는 정보의 대표 예:

```text
announcement_key
announcement_db_id
document_db_id
filename
storage_path
format
```

## 8.2 처리 완료 후 결과 저장

```python
persist_document_outputs(document_id)
```

처리 결과를 DB의 ProcessingRun 및 하위 데이터 구조에 저장합니다.

관련 주요 테이블:

```text
announcements
documents
processing_runs
document_structures
chunk_sets
chunks
embeddings
key_information
```

Embedding은 pgvector 검색에서 사용할 수 있도록 DB에 연결됩니다.

---

# 9. 핵심정보 추출

### 파일

```text
pipeline/key_information_extractor.py
```

### 진입 함수

```python
extract_key_information(...)
```

### 입력

주로 최종 구조화 JSON과 Verification 결과를 사용합니다.

### 현재 추출 대상

서비스에서 사용하는 대표 핵심정보는 다음과 같습니다.

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

### 처리 특징

- Section/Domain 정보 활용
- 키워드 기반 후보 탐색
- 날짜 범위 정규화
- 공급정보 후보 검증
- 전화번호 추출
- 구조화 Key-Value 활용
- 필요한 경우 여러 후보를 요약

### 저장

```text
pipeline.document_processor
    ↓ Python import
backend.app.services.key_information_service.upsert_key_information()
    ↓ DB
key_information
```

---

# 10. ProcessingRun 활성화 규칙

최신 Pipeline에서 중요한 안정성 규칙입니다.

`persist_document_outputs()`가 실행되면 새로운 ProcessingRun이 생성되지만 즉시 활성화하지 않습니다.

초기 상태:

```text
is_active = False
```

그 후 다음이 모두 성공해야 합니다.

```text
문서 Pipeline 성공
+ Persistence 성공
+ 핵심정보 추출 성공
+ 핵심정보 DB 저장 성공
```

마지막에만:

```python
activate_processing_run(processing_run_id)
```

를 호출합니다.

핵심정보 추출/저장 중 실패하면:

- 새 ProcessingRun을 failed 처리
- 새 Run은 활성화하지 않음
- 기존 정상 active ProcessingRun 유지
- 기존 정상 KeyInformation 유지

이 구조는 재처리 실패 때문에 서비스 중인 정상 데이터까지 깨지는 것을 방지하기 위한 것입니다.

---

# 11. 다른 파트와의 연결 관계

이 부분은 Docker/서비스 분리 시 가장 중요합니다.

| 연결 대상 | 현재 방식 | 전달 데이터 | 관련 코드 |
|---|---|---|---|
| Crawler → Backend DB | Python/DB | 공고 + 원본 Document 정보 | `collection_service.py` |
| Backend → Pipeline | Python import | `document_id` | `pipeline_gateway.py` |
| Pipeline → 원본 파일 | 파일 | `storage_path` | `document_processor.py` |
| Pipeline Stage 간 | 파일 + subprocess | JSON / NPY | `document_processor.py` |
| Pipeline → DB | Python import + DB | 구조/청크/임베딩 | `pipeline_persistence.py` |
| Pipeline → 핵심정보 저장 | Python import + DB | 7개 핵심정보 | `key_information_service.py` |
| DB → RAG | DB/pgvector | Chunk + Embedding | `rag/db_pipeline.py` |

현재 문서처리 자체를 호출하기 위한 별도 HTTP API는 없습니다.

관리자 HTTP Endpoint가 존재하지만 Endpoint 내부에서는 같은 서버의 Python 함수를 import하여 호출합니다.

---

# 12. 실제 호출 순서

## 관리자 재처리 기준

```text
Frontend/Admin
    ↓ HTTP
POST /documents/{document_id}/reprocess
    ↓
backend/app/api/routes/admin.py
run_document_reprocess()
    ↓ Python import
backend/app/services/pipeline_gateway.py
reprocess_document()
    ↓ env dynamic import
pipeline.document_processor:reprocess_document
    ↓
pipeline/document_processor.py
process_document()
    ↓ DB
get_registered_document_context()
    ↓ FILE
원본 HWP/HWPX
    ↓
Format Detection
    ↓ subprocess
Parser
    ↓ FILE
Parsed JSON
    ↓ subprocess
Normalizer
    ↓ FILE
Normalized JSON
    ↓ subprocess
Structure
    ↓ FILE
Structured JSON + Verification
    ↓ subprocess
Chunking
    ↓ FILE
chunks.json
    ↓ subprocess
Embedding
    ↓ FILE
embeddings.npy + metadata.json
    ↓ Python import + DB
persist_document_outputs()
    ↓
extract_key_information()
    ↓ Python import + DB
upsert_key_information()
    ↓ DB
activate_processing_run()
```

---

# 13. 데이터 흐름

핵심 데이터 변화는 다음과 같습니다.

```text
Document DB Row
(document_id, storage_path, format, announcement_id)
    ↓
원본 HWP/HWPX
    ↓
Parsed Document JSON
(paragraphs, tables, nested tables, metadata ...)
    ↓
Normalized Document JSON
    ↓
Structured Document JSON
(sections, hierarchy, domain, structured tables ...)
    ↓
Chunk JSON
(chunk_id, text, section/source metadata ...)
    ↓
Embedding
(chunk_id ↔ 1024차원 BGE-M3 vector)
    ↓
PostgreSQL / pgvector
    ↓
RAG Retrieval 대상 데이터
```

핵심정보는 별도 흐름으로 저장됩니다.

```text
Structured JSON
    ↓
extract_key_information()
    ↓
7개 핵심정보 Payload
    ↓
key_information table
    ↓
공고 상세 화면 등에서 사용
```

---

# 14. 실행환경

## Python 환경

서비스/문서처리 Pipeline은 프로젝트의 서비스용 Python 가상환경에서 실행합니다.

AWS에서 사용 중인 환경 예:

```bash
source ~/ddokbot/venvs/venv/bin/activate
```

## Parser 의존성

HWP/HWPX Parser는 Java Library를 사용합니다.

```text
pipeline/parser/libs/hwp/hwplib-1.1.10.jar
pipeline/parser/libs/hwpx/hwpxlib-1.0.8.jar
```

JPype/JVM 실행 환경이 필요합니다.

## Embedding

기본 모델:

```text
BAAI/bge-m3
```

현재 `.env.example`의 주요 설정:

```text
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_MODEL_PATH=/path/to/models/embedding/bge-m3
EMBEDDING_USE_FP16=true
EMBEDDING_REQUIRE_CUDA=true
EMBEDDING_DEVICE_INDEX=0
```

## Backend 연결

```text
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document
```

## PostgreSQL

```text
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
```

---

# 15. 정상 동작 확인 방법

문서 하나를 처리한 뒤 최소 다음을 확인해야 합니다.

## 파일

```text
01_parsed/<format>.json 존재
02_normalized/<format>.json 존재
03_structured/<format>/step4-1_value_normalized.json 존재
03_structured/<format>/step4-3_verification.json 존재
04_chunks/<format>/chunks.json 존재
05_embeddings/<format>/metadata.json 존재
05_embeddings/<format>/embeddings.npy 존재
```

## Verification

```text
status = pass
```

## DB

- 새로운 ProcessingRun이 생성되었는지
- Chunk/Embedding이 저장되었는지
- KeyInformation이 저장되었는지
- 최종 ProcessingRun이 active인지

## Runtime

해당 `announcement_id`에 질문했을 때 RAG가 저장된 Chunk를 정상 검색하는지 확인합니다.

---

# 16. 주요 트러블슈팅

## 16.1 확장자와 실제 문서 형식 불일치

### 문제

파일명이 `.hwp`라고 되어 있어도 실제 내부 구조가 HWPX이거나 반대인 사례가 있을 수 있습니다.

### 원인

확장자만 기준으로 Parser를 선택하면 잘못된 Library가 실행됩니다.

### 해결

`format_detector.py`를 추가해 내부 구조 기준으로 실제 형식을 판별합니다.

현재 서비스 Pipeline은 DB format과 실제 format이 다르면 오류를 발생시켜 Crawler 저장 정보를 확인하도록 합니다.

---

## 16.2 HWP/HWPX 특수 문자 및 번호 깨짐

### 문제

문단 번호나 표 내부 번호가 PUA 영역 문자로 추출되거나 정상 문자열로 보이지 않는 경우가 있습니다.

### 해결 방향

Parser에서 PUA 문자 위치와 복구 정보를 추적하고, 필요한 번호 문자 복원 로직을 적용했습니다.

원문 보존이 중요한 부분은 Parser에서 무조건 변환하지 않고 Normalizer/후속 단계와 역할을 나눴습니다.

---

## 16.3 표를 단순 텍스트화하면 정보 관계 손실

### 문제

LH 공고문의 공급정보, 임대조건, 소득/자산 기준 등이 표에 많습니다.

셀 텍스트만 순서대로 이어 붙이면 Header와 Value 관계가 사라집니다.

### 해결

`build_table_step3.py`에서 Header와 값의 관계, 병합 셀, 중첩 표를 구조화합니다.

---

## 16.4 연도가 생략된 날짜 범위

예:

```text
'26.8.31 ~ 9.2
```

### 문제

두 번째 날짜에 연도가 없으면 단순 날짜 정규화에서 다른 값으로 처리될 수 있습니다.

### 영향

`application_period`, `winner_announcement` 등 핵심정보가 잘못 저장될 수 있습니다.

### 대응

`key_information_extractor.py`에서 날짜 범위와 앞뒤 문맥을 함께 해석하도록 보완하고 있습니다.

---

## 16.5 재처리 도중 실패 시 기존 서비스 데이터 손상 가능성

### 문제

새 문서처리 Run이 중간에 실패했는데 새 Run을 바로 active로 만들면 정상 서비스 데이터가 깨질 수 있습니다.

### 해결

새 ProcessingRun은 기본 비활성 상태로 저장하고 핵심정보 저장까지 모두 성공했을 때만 `activate_processing_run()`을 호출하도록 구성했습니다.

---

# 17. 변경 시 영향 범위

## Parser 출력 Schema 변경

확인해야 할 영역:

```text
Normalizer
Structure
테스트/Fixture
```

## Structure Schema 변경

확인해야 할 영역:

```text
Chunking
Key Information Extractor
Pipeline Persistence
RAG 검색 Context
Evaluation reference/retrieved_contexts 분석
```

## Chunk Schema 변경

확인해야 할 영역:

```text
Embedding
DB Persistence
RAG Retrieval
Evaluation
```

## Embedding dimension/model 변경

확인해야 할 영역:

```text
DB pgvector column
Embedding metadata validation
RAG query embedding
Retrieval
Evaluation
```

따라서 문서처리에서 필드를 변경할 때는 해당 JSON만 수정하고 끝내지 말고 **그 값을 소비하는 다음 Stage를 확인해야 합니다.**

---

# 18. 현재 구조에서 알아야 할 사항

## 18.1 Python import 의존

Backend와 Pipeline 연결은 HTTP가 아니라 환경변수 기반 Python import입니다.

```text
DOCUMENT_REPROCESSOR
→ pipeline.document_processor:reprocess_document
```

같은 Python 환경/코드베이스를 전제로 합니다.

## 18.2 파일 시스템 의존

Parser → Normalizer → Structure → Chunk → Embedding 단계가 중간 JSON/NPY 파일을 공유합니다.

즉 동일한 파일 시스템에 접근할 수 있다는 전제가 있습니다.

## 18.3 subprocess 의존

`document_processor.py`는 각 Pipeline Stage를 별도 Python subprocess로 실행합니다.

Docker로 Stage를 완전히 분리할 경우 현재 호출 방식은 그대로 사용할 수 없습니다.

## 18.4 DB가 먼저 준비되어 있어야 함

서비스용 `process_document(document_id)`는 시작부터 DB의 Document row와 `storage_path`를 조회합니다.

원본 파일만 가지고 바로 실행하는 함수가 아니라 **등록된 Document ID를 기준으로 동작하는 통합 Pipeline**입니다.

---

# 19. Docker 분리 전 확인할 부분

현재 구조를 Docker/서비스 단위로 분리한다면 다음을 우선 확인해야 합니다.

## Backend ↔ Pipeline

현재:

```text
Python import
```

분리 후 후보:

```text
HTTP API / Message Queue / Worker
```

## Pipeline Stage 간 파일 공유

현재:

```text
로컬 파일 경로
```

분리 후에는 다음 중 하나가 필요할 수 있습니다.

```text
공유 Volume
Object Storage
Stage 간 API 전달
```

## Parser Java Library

Parser Container에는 JVM과 HWP/HWPX JAR가 포함되어야 합니다.

## Embedding GPU

Embedding Container를 별도로 분리하면 GPU 접근 설정과 모델 경로 공유가 필요합니다.

## DB 연결

Pipeline Container가 PostgreSQL에 직접 접근할지 Backend를 통해 저장할지 결정해야 합니다.

현재는 Pipeline 코드가 `backend.app.services.pipeline_persistence`를 직접 import하고 DB에 접근합니다.

---

# 20. 신규 개발자가 먼저 읽을 파일

문서처리 문제를 이어서 수정해야 한다면 다음 순서로 읽는 것을 권장합니다.

```text
1. pipeline/document_processor.py
   ↓
2. pipeline/parser/format_detector.py
   ↓
3. pipeline/parser/hwp_parser.py / hwpx_parser.py
   ↓
4. pipeline/normalizer/document_normalizer.py
   ↓
5. pipeline/structure/run_structure.py
   ↓
6. build_document_step1.py
   ↓
7. build_domain_step2.py
   ↓
8. build_table_step3.py
   ↓
9. value_normalizer.py / verification.py
   ↓
10. pipeline/key_information_extractor.py
   ↓
11. backend/app/services/pipeline_persistence.py
```

처음부터 모든 파일의 세부 구현을 읽기보다 `document_processor.py`에서 전체 호출 순서를 먼저 이해한 후 문제가 발생한 Stage로 내려가는 것이 효율적입니다.

---


# 21. 후임자가 반드시 알아야 할 데이터 필드

문서처리 코드를 수정할 때는 함수 이름보다 **Stage 사이에서 어떤 필드가 계약처럼 사용되는지**를 먼저 이해하는 것이 중요합니다.

## 21.1 Parser / Normalizer에서 자주 확인하는 필드

대표적으로 다음 필드를 확인합니다.

```text
type
text
search_text
source
paragraphs
tables
cells
blocks
row
col
row_span
col_span
nested_depth
```

특히 표 관련 문제에서는 다음을 함께 확인합니다.

```text
row / col
→ 셀의 시작 위치

row_span / col_span
→ 병합 범위

blocks
→ 셀 내부의 문단 또는 중첩 표

nested_depth
→ 중첩된 표인지 판단할 때 참고
```

`text`와 `search_text`는 목적이 다릅니다.

```text
text
→ 원문 의미와 표시 내용을 최대한 보존

search_text
→ 검색/비교에 사용하기 쉽도록 정리한 문자열
```

따라서 검색 품질을 높이기 위해 `text` 자체를 과도하게 변형하지 않는 것이 중요합니다.

## 21.2 Structure에서 자주 확인하는 필드

구조화 결과를 확인할 때는 다음 필드를 우선 봅니다.

```text
sections
title
level
marker
domain
contents
tables
columns
rows
header_path
merged_values
normalized_value
```

제목 문제가 발생한 경우:

```text
title
level
marker
```

를 먼저 확인하고,

표의 Header-Value 관계 문제가 발생한 경우:

```text
columns
rows
header_path
merged_values
```

를 확인합니다.

## 21.3 Chunk 이후 자주 확인하는 값

문서처리 결과는 최종적으로 Chunking에서 검색 단위로 변환됩니다.

후임자가 문서처리 필드를 수정했다면 최소한 다음이 정상인지 확인해야 합니다.

```text
chunk text
section/title 정보
table context
source 정보
document_id
announcement_id
```

Structure JSON에서 정보가 정상이어도 Chunk에 반영되지 않으면 RAG에서는 해당 정보를 검색할 수 없습니다.

---

# 22. 주요 함수 호출 관계 요약표

세부 구현을 모두 읽기 전에 아래 관계를 먼저 이해하는 것이 좋습니다.

| 영역 | 대표 함수 | 입력 | 주요 처리 | 출력/다음 단계 | 호출 주체 |
| --- | --- | --- | --- | --- | --- |
| 통합 Pipeline | `process_document()` | `document_id` | 전체 Stage 순차 실행 | DB 적재 및 활성 Run | `reprocess_document()` |
| 형식 판별 | `detect_actual_document_format()` | 원본 파일 경로 | 실제 HWP/HWPX 내부 형식 확인 | `"hwp"` / `"hwpx"` | `process_document()` |
| HWP Parser | `parse_hwp()` | HWP 파일 | 문단/표/중첩 표 추출 | Parsed JSON | Parser CLI/통합 Pipeline |
| HWPX Parser | `parse_hwpx()` | HWPX 파일 | 문단/표/중첩 표 추출 | Parsed JSON | Parser CLI/통합 Pipeline |
| HWP 중첩 표 | `find_nested_tables_in_hwp_cell()` | HWP 셀 객체 | 셀 내부 Control 순회 | 중첩 Table 목록 | HWP `parse_table()` |
| HWPX 중첩 표 | `find_nested_tables_in_hwpx_cell()` | HWPX 셀 객체 | 셀 내부 Run/RunItem 순회 | 중첩 Table 목록 | HWPX `parse_table()` |
| Normalizer | `normalize_document()` | Parsed JSON | 문자열/셀/표/검색용 필드 정규화 | Normalized JSON | Normalizer CLI |
| 제목 분석 | `parse_marker()` | 문단 텍스트 | 제목 번호 패턴 분석 | marker 정보 | Structure Step 1 |
| 제목 체계 추론 | `infer_heading_scheme()` | heading 후보 | 문서 전체 번호 체계 분석 | heading scheme | Structure Step 1 |
| 계층 할당 | `assign_levels()` | heading 후보 | 제목 수준 결정 | level이 부여된 항목 | Structure Step 1 |
| Section 생성 | `build_hierarchy()` | 구조 후보 | 계층형 Section 구성 | Section tree | Structure Step 1 |
| 표 분석 | `analyze_table()` | Table | Header/Value/병합 분석 | 구조화 Table | Structure Step 3 |
| 중첩 표 순회 | `iter_tables_recursive()` | 구조화 문서 | `cell.blocks`까지 재귀 탐색 | 모든 Table | Structure Step 3 |
| 값 정규화 | `normalize_values()` | Structured JSON | 날짜/금액/면적/전화번호 등 값 분석 | 정규화된 구조 | Structure Pipeline |
| 검증 | `verify_document()` | Structured JSON | 구조 이상 검사 | Verification JSON | `run_structure.py` |
| 핵심정보 | `extract_key_information()` | Structure + Verification | 핵심정보 7개 필드 추출 | 핵심정보 dict | `document_processor.py` |
| DB 적재 | `persist_document_outputs()` | `document_id` | 구조/Chunk/Embedding 저장 | `processing_run_id` | `process_document()` |

이 표는 전체 호출 흐름을 빠르게 파악하기 위한 요약이며, 세부 인자와 반환값은 실제 함수 정의를 기준으로 확인해야 합니다.

---

# 23. 오류 코드와 실패 Stage를 보는 방법

`pipeline/document_processor.py`에서는 Pipeline 오류를 `DocumentProcessingError`로 감싸고 **어느 Stage에서 실패했는지** 구분합니다.

대표적인 Stage는 다음과 같습니다.

```text
prepare
format_detection
parser
normalizer
structure
chunking
embedding
persistence
key_information
```

핵심정보 단계에서는 추가로 다음과 같은 오류가 구분됩니다.

```text
KEY_INFORMATION_VALIDATION_FAILED
KEY_INFORMATION_REQUIRED_FIELD_MISSING
KEY_INFORMATION_PERSISTENCE_FAILED
KEY_INFORMATION_EXTRACTOR_NOT_CONFIGURED
KEY_INFORMATION_EXTRACTOR_NOT_CALLABLE
KEY_INFORMATION_EXTRACTION_FAILED
```

에러가 발생했을 때는 메시지만 보고 수정하지 말고 먼저 **Stage를 기준으로 담당 파일을 좁히는 것**이 좋습니다.

예:

```text
stage=format_detection
→ format_detector.py / Crawler의 format 저장값 확인

stage=parser
→ hwp_parser.py 또는 hwpx_parser.py

stage=normalizer
→ document_normalizer.py

stage=structure
→ run_structure.py + Step1/2/3 + verification.py

stage=chunking
→ pipeline/chunking/

stage=embedding
→ pipeline/embedding/

stage=persistence
→ backend/app/services/pipeline_persistence.py

stage=key_information
→ key_information_extractor.py
```

---

# 24. 실제 디버깅 순서

RAG에서 잘못된 답변이 발견됐을 때 문서처리 담당자가 가장 먼저 해야 할 일은 **원문부터 LLM까지 한꺼번에 보는 것이 아니라 데이터가 처음 잘못된 Stage를 찾는 것**입니다.

권장 순서는 다음과 같습니다.

```text
1. 원본 HWP/HWPX
   ↓
2. Parsed JSON
   ↓
3. Normalized JSON
   ↓
4. Structured JSON
   ↓
5. Verification JSON
   ↓
6. chunks.json
   ↓
7. DB chunks / embeddings
   ↓
8. Retrieval 결과
   ↓
9. LLM 답변
```

예를 들어 원본 표에 `"임대보증금 12,345,000원"`이 있는데 챗봇이 해당 금액을 찾지 못했다면:

```text
Parsed JSON에 금액 없음
→ Parser

Parsed에는 있고 Normalized에 없음/변형됨
→ Normalizer

Normalized에는 있지만 잘못된 Section 또는 표 관계
→ Structure

Structure에는 정상인데 Chunk에 없음
→ Chunking

Chunk에는 정상인데 검색되지 않음
→ Embedding / Retrieval

검색 Context에는 정상인데 답변이 틀림
→ Generation / Prompt
```

이 방식으로 보면 다른 담당 파트와 문제 원인을 구분하기 쉽습니다.

---

# 25. 기능별로 어디를 보면 되는가

후임자가 기능을 수정하거나 동작 방식을 확인할 때는 프로젝트 전체를 검색하기보다 **기능 → 파일 → 함수** 순서로 보는 것이 가장 빠릅니다.

| 알고 싶은 기능 | 확인할 파일 | 주요 함수/대상 |
| --- | --- | --- |
| 실제 HWP/HWPX 형식 판별 | `pipeline/parser/format_detector.py` | `detect_actual_document_format()` |
| HWP 본문/표 파싱 | `pipeline/parser/hwp_parser.py` | `parse_hwp()`, `parse_table()` |
| HWP 셀 내부 중첩 표 탐색 | `pipeline/parser/hwp_parser.py` | `find_nested_tables_in_hwp_cell()` |
| HWPX 본문/표 파싱 | `pipeline/parser/hwpx_parser.py` | `parse_hwpx()`, `parse_table()` |
| HWPX 셀 내부 중첩 표 탐색 | `pipeline/parser/hwpx_parser.py` | `find_nested_tables_in_hwpx_cell()` |
| 공통 Parser 데이터 구조 | `pipeline/parser/common.py` | 공통 변환/직렬화 관련 함수 |
| 문자/텍스트 정규화 | `pipeline/normalizer/document_normalizer.py` | `normalize_document()` |
| 제목 번호 패턴 판별 | `pipeline/structure/build_document_step1.py` | `parse_marker()` |
| 문서 전체 제목 체계 추론 | `pipeline/structure/build_document_step1.py` | `infer_heading_scheme()` |
| 제목 계층 level 결정 | `pipeline/structure/build_document_step1.py` | `assign_levels()` |
| Section 계층 생성 | `pipeline/structure/build_document_step1.py` | `build_hierarchy()` |
| Domain 분류 규칙 | `pipeline/structure/domain_rules.json` | 규칙 데이터 |
| Domain 적용 | `pipeline/structure/build_domain_step2.py` | Domain 분류 관련 함수 |
| 표 Header-Value 구조화 | `pipeline/structure/build_table_step3.py` | `analyze_table()` |
| 중첩 표 재귀 순회 | `pipeline/structure/build_table_step3.py` | `iter_tables_recursive()` |
| 병합 셀 처리 | `pipeline/structure/build_table_step3.py` | `cell_range()`, `build_grid()`, `build_merged_value()` |
| 날짜/금액/면적 등 값 정규화 | `pipeline/structure/value_normalizer.py` | `normalize_values()` |
| 구조화 결과 검증 | `pipeline/structure/verification.py` | `verify_document()` |
| Structure 전체 실행 | `pipeline/structure/run_structure.py` | Structure 단계 orchestration |
| 핵심정보 추출 | `pipeline/key_information_extractor.py` | `extract_key_information()` |
| 전체 문서처리 실행 | `pipeline/document_processor.py` | `process_document()` |
| DB 적재 | `backend/app/services/pipeline_persistence.py` | `persist_document_outputs()` |

## 25.1 중첩 표를 확인할 때

중첩 표 처리는 Parser와 Structure 두 단계에서 모두 확인해야 합니다.

### HWP

```text
pipeline/parser/hwp_parser.py
→ find_nested_tables_in_hwp_cell()
→ 셀 내부 Paragraph
→ Control 목록 순회
→ Table 객체 발견
→ parse_table() 재귀 호출
```

### HWPX

```text
pipeline/parser/hwpx_parser.py
→ find_nested_tables_in_hwpx_cell()
→ 셀 내부 Paragraph
→ Run
→ RunItem 순회
→ Table 객체 발견
→ parse_table() 재귀 호출
```

### Structure

```text
pipeline/structure/build_table_step3.py
→ iter_tables_recursive()
→ Table
→ Cell
→ blocks
→ Nested Table
```

즉, 중첩 표 문제가 발생하면 **Parser에서 실제 중첩 표를 찾았는지**와 **Structure에서 `cell.blocks` 안의 표까지 다시 순회했는지**를 모두 확인해야 합니다.

## 25.2 병합 셀을 확인할 때

병합 셀 관련 문제는 다음 필드를 우선 확인합니다.

```text
row
col
row_span
col_span
merged_values
```

관련 코드는 주로 다음에 있습니다.

```text
pipeline/structure/build_table_step3.py
```

대표 함수:

```text
cell_range()
build_grid()
build_merged_value()
build_row_record()
```

세로 병합과 가로 병합을 동일하게 처리하지 않기 때문에 `row_span`, `col_span`, `merged_values`를 함께 봐야 합니다.

## 25.3 제목/Section 문제를 확인할 때

제목이 누락되거나 잘못된 level로 들어가면 다음 순서로 확인합니다.

```text
parse_marker()
→ heading candidate 판별
→ infer_heading_scheme()
→ assign_levels()
→ build_hierarchy()
```

확인 파일:

```text
pipeline/structure/build_document_step1.py
```

번호 없는 제목이 잘못 처리되는 경우에도 이 단계에서 후보 판별 규칙과 주변 문맥 규칙을 확인합니다.

## 25.4 정말 필요한 경우에만 코드 검색

함수 위치가 바뀌었거나 이름을 정확히 모를 때만 검색 명령어를 사용합니다.

예:

```bash
grep -Rni "find_nested_tables" pipeline/parser
```

제목 관련 코드를 찾을 때:

```bash
grep -Rni "parse_marker\|infer_heading_scheme\|assign_levels" pipeline/structure
```

출력 JSON에서 특정 원문이 어느 Stage까지 남아 있는지 확인할 때:

```bash
grep -Rni "임대보증금" outputs/<document>/
```

검색 명령어는 보조 수단이며, 기본적으로는 위의 **기능별 파일/함수 표를 먼저 참고하는 것을 권장합니다.**


# 26. 테스트와 검증 시 최소 확인 항목

현재 코드를 수정한 뒤에는 **실행 성공 여부만 확인하면 부족합니다.**

최소한 다음을 확인하는 것이 좋습니다.

## Parser 수정 후

- 일반 문단 수가 비정상적으로 감소하지 않았는가
- 최상위 표가 누락되지 않았는가
- 중첩 표가 유지되는가
- 셀 `row/col/row_span/col_span`이 유지되는가
- 원문에 있던 핵심 텍스트가 Parsed JSON에 존재하는가

## Normalizer 수정 후

- Parser의 구조가 유지되는가
- 깨진 문자/PUA 처리가 의도대로 동작하는가
- `text`의 의미가 손실되지 않는가
- `search_text`가 생성되는가
- 날짜/금액/단위 등이 과도하게 변경되지 않는가

## Structure 수정 후

- 제목이 올바른 Section에 들어가는가
- Section level이 과도하게 깊어지거나 평탄화되지 않는가
- Domain이 잘못 분류되지 않는가
- 표의 Header-Value 관계가 유지되는가
- 중첩 표가 사라지지 않는가
- `verification.json`의 오류/경고가 증가하지 않았는가

## 전체 Pipeline 수정 후

- Chunk가 정상 생성되는가
- Embedding 개수와 Chunk 개수가 맞는가
- DB Persistence가 성공하는가
- 핵심정보 7개 필드가 모두 생성되는가
- ProcessingRun이 성공한 경우에만 활성화되는가
- 실제 RAG Retrieval에서 해당 정보를 찾을 수 있는가

---

# 27. 현재 테스트 코드에서 알아둘 점

최신 코드에는 핵심정보 추출과 Backend 통합 관련 테스트가 존재합니다.

대표적으로:

```text
tests/backend/test_key_information_extractor.py
tests/backend/test_integration_service.py
tests/backend/test_backend_contracts.py
```

반면 현재 업로드된 코드 기준으로 Parser / Normalizer / Structure 전용 테스트 파일은 별도로 두드러지게 분리되어 있지 않습니다.

따라서 해당 영역을 수정할 때는 실제 LH 문서를 이용한 단계별 결과 비교가 중요합니다.

향후 자동 테스트를 보강한다면 다음 사례를 Fixture로 고정하는 것이 유용합니다.

```text
일반 문단 문서
최상위 표가 많은 문서
병합 셀이 있는 문서
중첩 표가 있는 문서
번호 없는 제목이 있는 문서
PUA/특수문자가 포함된 문서
확장자와 실제 내부 형식이 다른 문서
연도가 생략된 날짜 범위가 있는 문서
```

이는 새로운 기능 개발을 위한 고도화라기보다, **현재 문서처리 품질이 수정 과정에서 다시 깨지는 것을 막기 위한 회귀 테스트 대상**입니다.

---

# 28. 코드 수정 전 영향 범위 체크리스트

문서처리 코드를 수정하기 전에 다음 순서로 확인하면 실수를 줄일 수 있습니다.

- [ ] 수정하려는 값이 Parser 원문 필드인지 검색용 파생 필드인지 확인
- [ ] 해당 필드를 읽는 다음 Stage를 `grep`으로 검색
- [ ] HWP와 HWPX 양쪽에 같은 개념의 처리가 존재하는지 확인
- [ ] 일반 표뿐 아니라 병합 셀과 중첩 표에 영향이 없는지 확인
- [ ] Structure 변경이면 Chunking이 해당 필드를 사용하는지 확인
- [ ] Chunk 변경이면 Embedding/Persistence/Retrieval 영향을 확인
- [ ] 핵심정보 추출에 사용하는 Section/Domain/Table 구조가 바뀌지 않는지 확인
- [ ] 이전에 정상 처리되던 고정 문서로 회귀 확인
- [ ] `verification.json`의 경고/오류 변화 확인
- [ ] DB에 새 ProcessingRun이 정상 저장되는지 확인
- [ ] 실패 Run이 active 상태가 되지 않는지 확인
- [ ] 실제 RAG 검색 결과에서 필요한 Context가 유지되는지 확인

---

# 29. 이 문서에서 다루는 범위와 담당 경계

문서처리 파트는 전체 Ingestion Pipeline과 연결되기 때문에 Chunking, Embedding, DB 코드가 문서에 등장하지만 모든 내부 알고리즘이 문서처리 담당 범위라는 의미는 아닙니다.

구분하면 다음과 같습니다.

```text
직접 이해·수정해야 하는 핵심 영역
- format_detector
- HWP/HWPX Parser
- Normalizer
- Structure
- Verification
- Key Information Extractor
- document_processor의 전체 연결

연결 계약을 이해해야 하는 영역
- Chunking
- Embedding
- Pipeline Persistence
- PostgreSQL/pgvector
- Backend pipeline_gateway
- RAG Retrieval
```

후임자가 문서처리 문제를 수정할 때는 연결 영역의 구현 전체를 먼저 분석하기보다 **문서처리 출력이 다음 Stage의 입력 계약을 만족하는지**를 우선 확인하면 됩니다.

---

# 30. 작업을 이어받았을 때 권장 확인 순서

처음 프로젝트를 받은 개발자는 다음 순서로 확인하는 것을 권장합니다.

```text
1. 이 문서의 1~4장
   → 문서처리의 목적과 전체 흐름 이해

2. pipeline/document_processor.py
   → 실제 Stage 호출 순서 확인

3. 테스트용 HWP/HWPX 한 건 실행
   → outputs 디렉터리의 Stage별 결과 직접 확인

4. parser/normalizer/structure 코드
   → 각 Stage가 출력 JSON을 만드는 방식 확인

5. 병합 셀/중첩 표/제목 계층 사례 확인
   → 일반 텍스트 추출과 다른 핵심 처리 방식 이해

6. pipeline_persistence.py
   → 최종 결과가 DB에 어떤 형태로 저장되는지 확인

7. RAG Retrieval 결과 확인
   → 문서처리 결과가 실제 검색에 어떻게 사용되는지 확인
```

이 순서를 따르면 세부 함수부터 읽는 것보다 전체 구조를 훨씬 빠르게 파악할 수 있습니다.

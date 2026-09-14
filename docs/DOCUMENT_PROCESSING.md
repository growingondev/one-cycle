# DDOKBOT 문서처리 파트

> 이 문서는 OneCycle/DDOKBOT의 **문서처리 담당 영역**을 처음 보는 사람이 이 파일 하나만 읽고 전체 흐름을 이해할 수 있도록 정리한 문서입니다.
>
> 문서처리 담당 범위는 크게 다음 두 축입니다.
>
> 1. **HWP/HWPX 문서 처리**: 형식 판별 → Parsing → Normalization → Structuring / Verification
> 2. **Key Information Extraction**: 구조화된 문서에서 사용자 화면에 필요한 핵심정보 추출
>
> Chunking, Embedding, RAG, Backend DB Persistence, Frontend Rendering은 다른 영역이지만 문서처리 결과와 연결되므로 필요한 수준에서만 함께 설명합니다.
>
> **기준 상태: 2026-09-12**

---

# 1. 문서처리 파트가 하는 일

LH 임대주택 공고는 HWP/HWPX 형식으로 제공되며, 중요한 정보가 단순 본문뿐 아니라 표, 병합 셀, 중첩표, 제목 계층 안에 함께 들어 있습니다.

따라서 원문 파일에서 텍스트만 꺼내는 것으로는 충분하지 않습니다.

문서처리 파트의 목적은 다음과 같습니다.

```text
원본 HWP/HWPX
    ↓
문서 내부 형식 확인
    ↓
문단 / 표 / 중첩표 추출
    ↓
깨진 문자와 표현 정리
    ↓
제목 계층 복원
    ↓
Section별 의미 분류
    ↓
표 Header-Value 관계 복원
    ↓
값 정규화 / 구조 검증
    ↓
검색·청킹에 사용 가능한 문서 구조 생성
    ↓
사용자 화면용 핵심정보 추출
```

즉, 문서처리의 핵심은 **원문에 있는 정보와 정보 사이의 관계를 최대한 보존하는 것**입니다.

예를 들어 아래 표를 단순 문자열로만 만들면:

```text
남양주마석2단지 46형 30 10
```

각 숫자가 무엇을 의미하는지 알기 어렵습니다.

문서처리에서는 이를 다음처럼 관계가 있는 구조로 유지하는 것이 목표입니다.

```text
단지명      → 남양주마석2단지
주택형      → 46형
건설호수    → 30
모집예비자수 → 10
```

이 구조가 유지되어야 이후 Chunking, RAG Retrieval, Key Information Extraction이 안정적으로 동작합니다.

---

# 2. 전체 서비스 안에서의 위치

현재 서비스 구조를 단순화하면 다음과 같습니다.

```text
Crawler / 관리자
        ↓
Backend
        ↓ HTTP
Document Worker
        ↓
[문서처리]
Format Detection
→ Parser
→ Normalizer
→ Structure / Verification
        ↓
Chunking
        ↓
Embedding Service
        ↓
[문서처리]
Key Information Extraction
        ↓
Document Worker Response
        ↓ HTTP
Backend
        ↓
DB Persistence
        ↓
RAG / Frontend
```

문서처리 담당의 중심 영역은 다음입니다.

```text
Format Detection
Parser
Normalizer
Structure
Verification
Key Information Extraction
```

다음 영역은 연결 관계는 이해하지만 별도 담당입니다.

```text
Chunking
Embedding
RAG Retrieval
LLM Generation
Backend DB Persistence
Frontend Rendering
```

---

# 3. 주요 폴더 구조

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
│       ├── hwp/
│       └── hwpx/
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

서비스 분리 이후에는 다음 코드와 연결됩니다.

```text
document_worker/
├── main.py
└── service.py

services/
└── embedding/
    ├── main.py
    └── client.py
```

API 연결 자체의 상세 설명은 `DOCUMENT_WORKER_API_EXPLANATION.md`에서 별도로 관리합니다.

---

# 4. 전체 처리 흐름 한눈에 보기

문서 한 건이 들어오면 다음 순서로 처리됩니다.

```text
1. 문서 파일 확인
2. 실제 HWP/HWPX 형식 판별
3. Parser 실행
4. Parser JSON 생성
5. Normalizer 실행
6. Normalized JSON 생성
7. Structure Step 1 - 문서 계층 생성
8. Structure Step 2 - Domain 분류 / 계층 보정
9. Structure Step 3 - 표 세부 구조화
10. Value Normalizer - 날짜/금액/면적 등 값 정규화
11. Verification - 구조 품질 검증
12. Chunking
13. Embedding
14. Key Information Extraction
15. Worker 응답
16. Backend Persistence
```

중요한 점은 각 단계가 앞 단계의 결과를 덮어쓰는 것이 아니라, **점점 더 의미가 풍부한 구조를 추가해 나간다**는 것입니다.

---

# 5. Format Detection

## 5.1 왜 확장자만 보면 안 되는가

파일명이 `.hwp`라고 해서 내부 형식도 반드시 HWP인 것은 아닙니다.

실제로 수집 과정에서 확장자와 내부 포맷이 다를 수 있기 때문에 Parser 선택 전에 실제 내부 형식을 확인합니다.

주요 파일:

```text
pipeline/parser/format_detector.py
```

가장 중요한 함수:

```python
detect_actual_document_format(file_path)
```

반환값:

```text
"hwp"
"hwpx"
"unknown"
```

---

## 5.2 HWP 판별

HWP 5.x는 OLE/CFBF 형식이므로 파일의 시작 바이트를 확인합니다.

대표 Signature:

```text
D0 CF 11 E0 A1 B1 1A E1
```

이 Signature가 확인되면 HWP로 판단합니다.

---

## 5.3 HWPX 판별

HWPX는 ZIP/XML 기반 패키지입니다.

하지만 ZIP이라고 해서 모두 HWPX는 아니기 때문에 `_looks_like_hwpx_zip()`에서 내부 파일도 확인합니다.

대표 확인 대상:

```text
Contents/content.hpf
Contents/section0.xml
Contents/section1.xml
mimetype
```

즉:

```text
파일 확장자
    ↓
신뢰하지 않음

파일 내부 Signature / ZIP 구조
    ↓
실제 포맷 결정
```

---

# 6. Parser 단계

Parser의 역할은 **원본 HWP/HWPX에서 의미 해석을 과도하게 하지 않고 문서 요소를 최대한 손실 없이 꺼내는 것**입니다.

Parser에서 중요한 것은:

```text
문단
표
셀 좌표
병합정보
중첩표
원본 위치 정보
```

를 보존하는 것입니다.

---

# 7. HWP Parser

주요 파일:

```text
pipeline/parser/hwp_parser.py
```

HWP는 `hwplib` Java 라이브러리를 JPype를 통해 사용합니다.

대표 Reader:

```text
kr.dogfoot.hwplib.reader.HWPReader
```

---

## 7.1 `parse_hwp()`

HWP Parser의 전체 진입 함수입니다.

```python
parse_hwp(...)
```

주요 역할:

```text
HWP JAR 로드
↓
JVM 준비
↓
HWPReader로 문서 읽기
↓
Section 순회
↓
Paragraph 추출
↓
Table 추출
↓
중첩 Table 추출
↓
공통 Parser JSON 생성
```

Parser 전체 동작을 이해하려면 먼저 이 함수를 보는 것이 좋습니다.

---

## 7.2 `extract_hwp_paragraph_text()`

```python
extract_hwp_paragraph_text(...)
```

HWP 문단의 실제 텍스트를 꺼내는 함수입니다.

단순 `getNormalString()` 호출만 하는 것이 아니라, HWP에서 사용되는 **글자 겹치기 컨트롤** 등에 의해 번호가 별도로 저장된 경우도 확인합니다.

예를 들어 원문에는 번호가 보이는데 일반 텍스트 추출 결과에서는 번호가 빠지는 경우가 있습니다.

이때 검증 가능한 경우만 복원합니다.

중요 원칙:

```text
확실한 근거가 있으면 복원
근거가 없으면 원문 유지
추측해서 숫자를 만들지 않음
```

---

## 7.3 `parse_table()`

HWP 표를 파싱하는 핵심 함수입니다.

```python
parse_table(...)
```

각 셀에서 다음 정보를 읽습니다.

```text
row
col
row_span
col_span
text
paragraphs
nested_tables
```

예:

```json
{
  "row": 2,
  "col": 1,
  "row_span": 2,
  "col_span": 1,
  "text": "46A"
}
```

`row_span`, `col_span`을 보존하는 이유는 Structure 단계에서 병합표를 복구해야 하기 때문입니다.

---

## 7.4 중첩표 탐색

중첩표는 **표의 셀 안에 또 다른 표가 들어 있는 구조**입니다.

HWP에서 중첩표 탐색의 핵심 함수:

```python
find_nested_tables_in_hwp_cell(...)
```

흐름:

```text
상위 Table
  ↓
Cell
  ↓
Cell 안 Paragraph
  ↓
Control List 탐색
  ↓
ControlTable 발견
  ↓
parse_table() 재귀 호출
```

각 중첩표에는 다음과 같은 Source Metadata가 붙습니다.

```text
parent_table_index
parent_cell
nested_depth
object_path
```

예:

```text
parent_table_index = 12
parent_cell = {"row": 3, "col": 1}
nested_depth = 2
```

이 값들 덕분에 **중첩표가 어느 표의 어느 셀에 있었는지** 추적할 수 있습니다.

---

## 7.5 중첩 깊이 제한

무한 재귀나 비정상 문서를 방지하기 위해 `max_nested_depth`를 사용합니다.

```text
depth >= max_nested_depth
→ 하위 표 탐색 중단
→ warning 기록
```

즉 Parser는 중첩표를 끝없이 탐색하지 않습니다.

---

## 7.6 번호 복원

HWP 공고에는 한컴 전용 PUA 문자나 글자 겹치기로 만들어진 번호가 있을 수 있습니다.

관련 함수:

```python
recover_hwp_table_item_numbers(...)
```

중요한 정책은 **숫자를 추측하지 않는 것**입니다.

예를 들어:

```text
-1
-2
```

앞 번호가 빠져 있다고 해서 주변 숫자를 임의로 붙이지 않습니다.

같은 열의 가까운 위치에 있는 **검증된 번호 Anchor**가 있을 때만 다음처럼 복원합니다.

```text
12
↓
12-1
12-2
```

근거가 없으면:

```text
원문 유지
+ unresolved warning 기록
```

으로 처리합니다.

---

# 8. HWPX Parser

주요 파일:

```text
pipeline/parser/hwpx_parser.py
```

대표 Reader:

```text
kr.dogfoot.hwpxlib.reader.HWPXReader
```

HWPX는 ZIP/XML 기반 형식이지만 서비스에서는 `hwpxlib`와 XML 보조 추출을 함께 사용합니다.

---

## 8.1 HWPX Parser의 목표

HWP와 HWPX는 내부 구조가 다르지만 후속 단계에서는 가능하면 같은 형태로 처리해야 합니다.

따라서 Parser 결과를 다음 공통 구조에 맞추는 것이 중요합니다.

```text
sections
paragraphs
tables
cells
nested_tables
source
```

이 덕분에 Normalizer 이후부터는 HWP/HWPX 별도 코드를 최소화할 수 있습니다.

---

## 8.2 PUA / Compose 처리

HWPX에도 일반 Unicode가 아닌 PUA 문자나 Compose가 존재할 수 있습니다.

Parser 단계의 원칙은:

```text
PUA 의미를 무리하게 해석하지 않음
원본 문자와 codepoint 보존
검증된 경우만 번호 복원
```

입니다.

관련 함수:

```python
recover_table_item_numbers(...)
```

검증된 `PUA map` 또는 `Compose map`을 Anchor로 사용하며, 일반 숫자나 주택형의 숫자를 번호로 착각하지 않도록 제한합니다.

예:

```text
55A
59A
```

이 값들은 주택형일 수 있으므로 제목 번호 Prefix로 사용하지 않습니다.

---

## 8.3 XML 보조 추출

대표 함수:

```python
load_hwpx_xml_top_level_paragraphs(...)
```

HWPX 내부 ZIP의 `section*.xml`을 직접 확인해 최상위 문단 텍스트를 보조 추출합니다.

라이브러리 결과에서 일부 문단 위치가 애매한 경우 원본 XML을 참고할 수 있게 만든 보조 경로입니다.

---

# 9. Parser 공통 출력에서 중요한 것

Parser 결과는 단순 텍스트 목록이 아닙니다.

대표적으로 다음 정보를 유지합니다.

```text
type
text
section_index
paragraph_index
table_index
row
col
row_span
col_span
nested_depth
parent_table_index
parent_cell
object_path
```

이 중 `source` 정보는 매우 중요합니다.

왜냐하면 나중에 문제가 생겼을 때:

```text
이 텍스트가 어느 Section에서 나왔는가?
어느 표의 몇 번째 셀인가?
중첩표인가?
```

를 추적해야 하기 때문입니다.

---

# 10. Normalizer 단계

주요 파일:

```text
pipeline/normalizer/document_normalizer.py
```

Normalizer의 역할은 **Parser가 추출한 원문 구조를 유지하면서 문자 표현과 공통 Schema를 안정화하는 것**입니다.

Parser와 Structure 사이의 완충 단계라고 생각하면 쉽습니다.

---

# 11. 왜 Normalizer가 필요한가

HWP와 HWPX Parser가 같은 내용을 추출해도 표현이 조금씩 다를 수 있습니다.

예:

```text
① 신청자격
1 신청자격

․
·

초성 자모
호환 자모

NBSP
일반 공백
```

이 상태로 Structure에서 문자열 비교를 하면 같은 제목도 서로 다른 값처럼 처리될 수 있습니다.

Normalizer는 이런 차이를 줄입니다.

---

# 12. 문자 정규화

대표 설정:

```python
VERIFIED_PRIVATE_USE_MAP
SAFE_CHARACTER_REPLACEMENTS
```

검증된 PUA만 일반 문자로 바꿉니다.

예:

```text
U+F0A0
→ ·
```

네모 숫자나 문자도 실제 원문과 대조해 확인된 값만 매핑합니다.

중요한 정책:

```text
검증된 PUA
→ 변환

검증되지 않은 PUA
→ 임의 변환하지 않음
→ warning 기록
```

---

## 12.1 안전한 문자 치환

예:

```text
NBSP              → 일반 공백
Zero-width space  → 제거
BOM               → 제거
․                 → .
‧                 → ·
①                 → 1
②                 → 2
```

행복주택 자격 추출에서 `①`, `②` 등이 `1`, `2`로 정규화되기 때문에 후속 정규식도 이 점을 고려해야 합니다.

---

# 13. Source Metadata 정규화

Normalizer는 Parser별 Source Metadata 차이도 정리합니다.

공통적으로 유지하는 값:

```text
section_index
paragraph_index
location
parent_table_index
parent_cell
nested_depth
object_path
```

포맷별 추적용 값:

```text
control_index
run_index
item_index
start_position
end_position
```

이렇게 하면 HWP/HWPX 모두 동일한 Source 추적 방식을 사용할 수 있습니다.

---

# 14. `NormalizationContext`

대표 클래스:

```python
NormalizationContext
```

문서 하나를 정규화하면서 통계와 Warning을 관리합니다.

예:

```text
section_count
paragraph_count
table_count
cell_count
empty_cell_count
unknown_block_count
unverified_pua_count
warnings
```

이 정보는 단순히 파일을 변환하는 것에서 끝나지 않고 **정규화 품질을 확인하는 용도**로 사용됩니다.

---

# 15. Parser와 Normalizer의 차이

두 단계를 혼동하기 쉽습니다.

```text
Parser
= 문서에서 요소를 꺼내는 단계

Normalizer
= 꺼낸 요소의 표현을 공통 형태로 정리하는 단계
```

예:

```text
HWP 셀 안의 텍스트와 병합정보 읽기
→ Parser

PUA 가운데점을 ·로 변경
→ Normalizer
```

즉 Parser가 **구조를 잃지 않고 추출**하고, Normalizer가 **표현 차이를 줄이는 역할**을 합니다.

---

# 16. Structure 단계 개요

Structure의 진입 파일:

```text
pipeline/structure/run_structure.py
```

핵심 함수:

```python
run_structure_pipeline(...)
```

Structure는 총 4개 핵심 흐름으로 볼 수 있습니다.

```text
Step 1
문서 계층 구조화

Step 2
Domain 분류 + 계층 보정

Step 3
표 Header-Value 구조화

Step 4
값 정규화 + Verification
```

---

# 17. Structure Step 1 - 문서 계층 만들기

주요 파일:

```text
pipeline/structure/build_document_step1.py
```

목표:

```text
평면적인 Paragraph/Table 순서
        ↓
제목과 본문 구분
        ↓
제목 Level 추론
        ↓
Section 계층 생성
```

출력:

```text
step1-1_items.json
step1-2_heading_scheme.json
step1-3_hierarchy.json
```

---

## 17.1 제목 후보 찾기

대표 함수:

```python
parse_marker(...)
paragraph_heading_candidate(...)
semantic_heading_candidate(...)
table_heading_candidate(...)
```

---

## 17.2 `parse_marker()`

강한 번호 표식이 있는 제목을 찾습니다.

지원 예:

```text
제1장
Ⅰ.
1.
1)
(1)
①
가.
1.1
```

하지만 날짜:

```text
2026.09.10.
```

를 `2026.`이라는 제목으로 오인하지 않도록 예외 처리합니다.

---

## 17.3 `semantic_heading_candidate()`

LH 문서에는 번호가 없는 제목도 있습니다.

예:

```text
■ 신청자격
■ 제출서류
계약 등 주요일정
```

이 함수는 다음 조건을 조합해 제목 가능성을 판단합니다.

```text
알려진 제목
제목형 Bullet
제목형 종결어
짧은 문장
뒤에 표가 존재하는지
```

일반 설명 문장을 제목으로 오인하지 않도록 보수적으로 동작합니다.

---

## 17.4 표 안에 들어 있는 제목

LH 공고는 레이아웃 때문에 제목 자체가 작은 표 안에 들어가 있는 경우가 있습니다.

대표 함수:

```python
table_heading_candidate(...)
```

1행, 소수 열로 구성된 작은 표에서 강한 제목 Marker를 발견하면 제목 후보로 처리합니다.

---

## 17.5 Layout Table과 Data Table 구분

대표 함수:

```python
is_layout_container(...)
```

일부 HWP 문서는 문서 전체 레이아웃을 큰 외곽 표 안에 넣습니다.

예:

```text
외곽 Table
└─ Cell
   ├─ 제목
   ├─ 본문
   ├─ 실제 데이터 Table
   └─ 다음 본문
```

이 외곽 표를 일반 데이터 표로 처리하면 제목과 문단 흐름을 잃게 됩니다.

따라서 Layout Container로 판단되면 셀 안의 Block을 실제 문서 흐름으로 펼칩니다.

---

# 18. Structure Step 2 - Domain 분류

주요 파일:

```text
pipeline/structure/build_domain_step2.py
pipeline/structure/domain_rules.json
```

출력:

```text
step2-1_normalized_titles.json
step2-2_domain_matches.json
step2-3_domain_tagged.json
step2-4_hierarchy_conflicts.json
step2-5_domain_repaired.json
```

---

## 18.1 Domain이란

Section이 어떤 의미의 영역인지 분류한 값입니다.

예:

```text
신청자격
공급정보
일정
제출서류
문의처
소득·자산
```

이 Domain은 Chunking과 Key Information Extraction에서 해당 Section을 찾는 데 도움이 됩니다.

---

## 18.2 `normalize_title()`

대표 함수:

```python
normalize_title(...)
```

Domain 비교 전에 제목에서 번호/괄호/기호를 제거합니다.

예:

```text
"4. 신청자격"
→ "신청자격"

"■ 소득 및 자산보유 기준"
→ 비교 가능한 제목 문자열
```

---

## 18.3 `build_classification_sources()`

Domain 판단에 제목만 사용하지 않습니다.

대표 함수:

```python
build_classification_sources(...)
```

다음 정보를 조합합니다.

```text
현재 제목
부모 제목
표 Header
Section 본문 일부
```

즉 제목이 애매해도 주변 문맥을 통해 분류할 수 있습니다.

---

## 18.4 계층 보정

Domain 분류만 하는 것이 아니라 잘못 들어간 Section 계층을 보수적으로 수정합니다.

중요 원칙:

```text
Domain 하나만 보고 무조건 이동하지 않음
연속된 Section인지 확인
다음 상위 Section과 의미가 일치하는지 확인
안전 조건이 만족될 때만 이동
```

애매한 경우에는 원래 구조를 유지합니다.

---

# 19. Structure Step 3 - 표 구조화

주요 파일:

```text
pipeline/structure/build_table_step3.py
```

출력:

```text
step3-1_table_headers.json
step3-2_table_mappings.json
step3-3_structured_tables.json
```

이 단계는 문서처리에서 매우 중요합니다.

LH 공고의 핵심 데이터 상당수가 표에 있기 때문입니다.

---

# 20. 표 Grid 복원

대표 함수:

```python
build_grid(...)
cell_range(...)
```

Parser가 저장한:

```text
row
col
row_span
col_span
```

을 이용해 논리적인 2차원 Grid를 다시 만듭니다.

예를 들어 원문에:

```text
        소득기준
      ┌────┬────┐
가구원수  70%   80%
```

처럼 병합 Header가 있어도 셀 범위를 이용해 실제 Header 관계를 복원합니다.

---

# 21. 병합 셀 처리

병합 셀은 크게 두 종류가 있습니다.

## 21.1 세로 병합

```text
row_span > 1
```

예:

```text
단지명: 남양주마석2
        ├─ 46A
        └─ 51A
```

단지명 셀이 여러 행에 걸쳐 병합되어 있다면 각 데이터 행이 어느 단지에 속하는지 연결해야 합니다.

세로 병합 값은 필요한 데이터 행에 상속합니다.

---

## 21.2 가로 병합

```text
col_span > 1
```

가로 병합된 데이터 값을 여러 Header에 동일한 값으로 복제하면 의미가 왜곡될 수 있습니다.

따라서 가로 병합 값은:

```text
record.merged_values
```

에 한 번만 저장하고, 어떤 Column 범위를 덮고 있었는지 별도 기록합니다.

---

# 22. Header-Value Mapping

표 구조화의 핵심 목표는:

```text
셀 좌표
→ Header Path
→ 실제 Value
```

를 연결하는 것입니다.

예:

```text
Header:
공급대상 > 모집인원수

Value:
0
```

최종적으로:

```text
모집인원수 → 0
```

이라는 관계가 만들어집니다.

이 관계가 Key Information에서 `recruitment_people = 0`으로 이어집니다.

---

# 23. 표 구조화 실패 시 처리

모든 표를 억지로 구조화하지 않습니다.

확실하지 않은 표는:

```text
structured
partially_structured
skipped
```

같은 상태를 남기고 원본 `cells`를 유지합니다.

이 정책이 중요한 이유는 잘못 구조화된 값이 원문보다 더 위험하기 때문입니다.

---

# 24. Value Normalizer

주요 파일:

```text
pipeline/structure/value_normalizer.py
```

이 파일은 `document_normalizer.py`와 이름이 비슷하지만 역할이 다릅니다.

```text
document_normalizer.py
= Parser 결과의 문자/문서 표현 정리

value_normalizer.py
= Structure 결과의 값 의미/타입 정규화
```

---

## 24.1 주요 함수

대표 함수:

```python
normalize_search_text(...)
```

원문 값을 덮어쓰지 않고 검색/임베딩용 텍스트를 추가합니다.

처리 대상:

```text
금액
날짜
시간
면적
전화번호
백분율
```

---

## 24.2 값 예시

원문:

```text
34,500만원
```

의미:

```text
money
```

원문:

```text
2026.09.10
```

의미:

```text
date
```

원문:

```text
73㎡
```

의미:

```text
area
```

이런 타입 정보는 후속 단계에서 값 비교와 검색 품질을 높이는 데 사용할 수 있습니다.

---

# 25. Verification

주요 파일:

```text
pipeline/structure/verification.py
```

대표 함수:

```python
verify_document(...)
```

Structure와 Value Normalizer가 끝난 결과를 최종 검증합니다.

---

## 25.1 검증 대상

예:

```text
Section이 존재하는가
Section ID가 중복되지 않는가
Domain 필드가 정상인가
Table 크기가 정상인가
Cell 병합 범위가 표 밖으로 나가지 않는가
Table 구조화 상태가 정상인가
classification_text가 비어 있지 않은가
```

---

## 25.2 Error와 Warning 구분

검증 결과는 단순 성공/실패만 반환하지 않습니다.

```text
error
warning
```

을 구분합니다.

최종 Status:

```text
error 존재
→ fail

error 없음 + warning 존재
→ warning

둘 다 없음
→ pass
```

즉 **실행 실패와 데이터 품질 경고를 분리**해서 확인할 수 있습니다.

---

# 26. Structure 전체 출력

`run_structure_pipeline()`이 실행되면 주요 결과는 다음과 같이 생성됩니다.

```text
03_structured/<format>/
├── step1-1_items.json
├── step1-2_heading_scheme.json
├── step1-3_hierarchy.json
│
├── step2-1_normalized_titles.json
├── step2-2_domain_matches.json
├── step2-3_domain_tagged.json
├── step2-4_hierarchy_conflicts.json
├── step2-5_domain_repaired.json
│
├── step3-1_table_headers.json
├── step3-2_table_mappings.json
├── step3-3_structured_tables.json
│
├── step4-1_value_normalized.json
├── step4-2_value_validation.json
└── step4-3_pipeline_verification.json
```

실제 Chunking과 Key Information에서 가장 중요한 결과는:

```text
step4-1_value_normalized.json
```

입니다.

---

# 27. 문서처리 단계별 핵심 요약

| 단계 | 핵심 질문 | 주요 결과 |
|---|---|---|
| Format Detection | 실제 파일 형식이 무엇인가? | hwp / hwpx |
| Parser | 문서에 무엇이 들어 있는가? | 문단, 표, 셀, 중첩표 |
| Normalizer | 표현 차이를 어떻게 통일할 것인가? | 공통 문자/Schema |
| Structure Step 1 | 제목과 본문 구조가 어떻게 연결되는가? | Section 계층 |
| Structure Step 2 | 각 Section은 어떤 의미인가? | Domain |
| Structure Step 3 | 표의 Header와 Value는 어떻게 연결되는가? | structured_table |
| Value Normalizer | 이 값은 날짜/금액/면적 중 무엇인가? | 타입/검색용 값 |
| Verification | 결과 구조가 안전한가? | pass/warning/fail |

---

# 28. Key Information Extraction

문서 파싱~구조화가 끝나면 사용자 화면에 바로 보여줄 핵심 정보를 별도로 추출합니다.

주요 파일:

```text
pipeline/key_information_extractor.py
```

최종 진입 함수:

```python
extract_key_information(...)
```

Key Information은 원본 문서를 다시 직접 파싱하지 않고, **Structure 결과를 사용**합니다.

즉 관계는 다음과 같습니다.

```text
Parser
↓
Normalizer
↓
Structure
↓
Key Information
```

---

# 29. Key Information 7개 필드

현재 추출 필드:

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

각 필드의 의미:

| 필드 | 설명 |
|---|---|
| `application_period` | 신청 시작일/마감일/기간 |
| `eligibility` | 신청자격, 공통조건, 계층별 세부조건 |
| `supply_information` | 공급 위치, 단지, 주택형, 공급수 |
| `income_asset_criteria` | 소득/총자산/자동차 기준 |
| `required_documents` | 제출 필요 서류 |
| `winner_announcement` | 당첨자/예비입주자 발표 |
| `contact_information` | 문의처/전화번호 |

---

# 30. Key Information Builder 구조

대표 함수:

```python
_build_application_period()
_build_eligibility()
_build_supply_information()
_build_income_asset_criteria()
_build_required_documents()
_build_winner_announcement()
_build_contact_information()
```

각 Builder는 Structure에서 관련 Section, 표, Domain, 텍스트를 탐색한 뒤 UI에서 사용하기 쉬운 형태로 정리합니다.

---

# 31. 신청기간

<<<<<<< HEAD
이 부분은 Docker/서비스 분리 시 가장 중요합니다.

| 연결 대상 | 현재 방식 | 전달 데이터 | 관련 코드 |
|---|---|---|---|
| Crawler → Backend | HTTP job API | 공고 + 원본 Document 정보 | `crawler_client.py`, `collection_service.py` |
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
=======
대표 처리 대상:
>>>>>>> 2c10a57 (docs: update document processing guide)

```text
2026.09.10 ~ 2026.09.12
2026.8.31 ~ 9.2
표 형식 일정
시간 포함 일정
```

중요한 문제 중 하나는:

```text
2026.8.31 ~ 9.2
```

처럼 뒤 날짜에서 연도가 생략되는 경우입니다.

이 경우 앞 날짜의 연도를 기준으로 해석합니다.

---

# 32. 신청자격

신청자격은 공고 유형별 차이가 커서 Key Information 중 가장 복잡한 영역입니다.

대표 구조:

```json
{
  "summary": "...",
  "common_conditions": [
    "무주택세대구성원"
  ],
  "target_groups": [
    {
      "code": "adult",
      "label": "성년자",
      "details": [
        "..."
      ]
    }
  ]
}
```

---

## 32.1 일반 국민임대 / 50년 공공임대

이 유형은 **신청자격과 선정기준을 분리하는 것**이 중요합니다.

공고 뒤쪽 선정기준에는:

```text
예비신혼부부
북한이탈주민
사회취약계층
한부모가족
```

등이 등장할 수 있지만, 이 값들이 모두 기본 신청대상이라는 뜻은 아닙니다.

따라서 실제:

```text
신청자격
입주자격
```

Section을 우선 사용하고 뒤의:

```text
선정기준
```

영역을 분리합니다.

대표 보조 함수:

```python
_standard_general_rental_eligibility_text(...)
_is_standard_general_rental_eligibility_structure(...)
```

---

## 32.2 성년자

국민임대 등에서는 `■ 성년자` 내용을 하나의 Target Group으로 구성합니다.

대표 함수:

```python
_extract_adult_eligibility_group_from_structure(...)
```

대표 출력:

```text
성년자

- 민법상 미성년자는 원칙적으로 신청 불가
- 자녀가 있는 미성년 세대주 예외
- 형제자매를 부양하는 미성년 세대주 예외
- 외국인 부모 + 미성년 자녀 한부모가족 예외
```

구조화 과정에서 첫 원칙 문장과 예외 Bullet이 서로 다른 노드로 나뉘는 경우가 있어, 실제 예외조건이 잡힌 경우 원칙도 함께 보존하도록 후처리합니다.

---

## 32.3 행복주택

행복주택은 신청 계층이 여러 Section으로 나뉘어 있습니다.

대표 계층:

```text
대학생
청년
산업단지 근로자
신혼부부·한부모가족
고령자
```

대표 함수:

```python
_extract_happyhouse_eligibility_target_groups_from_structure(...)
_happyhouse_group_spec_from_title(...)
```

Normalizer에서:

```text
① → 1
② → 2
```

로 바뀌는 점도 고려해서 제목을 인식합니다.

---

## 32.4 다자녀 매입임대

대표 함수:

```python
_is_multi_child_purchase_rental_structure(...)
_extract_multi_child_eligibility_group_from_structure(...)
```

대표 조건:

```text
2명 이상의 미성년 자녀
무주택세대구성원
소득기준
총자산
자동차가액
직계비속 정의
```

일반 자격 Group보다 Detail 수가 많을 수 있으므로 후처리에서 필요한 내용을 잘라내지 않도록 별도 처리합니다.

---

# 33. 소득 / 자산 기준

대표 함수:

```python
_build_income_asset_criteria(...)
_extract_standard_general_rental_income_asset_criteria(...)
_extract_multi_child_income_asset_criteria(...)
```

국민임대의 경우 다음처럼 표와 설명이 함께 존재할 수 있습니다.

```text
월평균 소득
70% | 80% | 90%

1인 가구 20% 가산
2인 가구 10% 가산
```

중요한 점은:

```text
20% 가산
```

을 기본 소득기준 `20%`로 오인하면 안 된다는 것입니다.

따라서 표의 기본 기준을 먼저 읽습니다.

최종 결과 예:

```text
월평균소득 70% 이하
(1인가구 90%, 2인가구 80%)
```

---

## 33.1 자산 단위 정규화

문서별 표현 차이:

```text
총자산 34,500만원
총자산 (345)백만원
```

둘은 같은 규모의 값을 표현할 수 있습니다.

자동차도:

```text
자동차 4,542만원
자동차가액 (4,542)만원
```

처럼 표현이 다릅니다.

Key Information에서는 사용자 화면에서 이해하기 쉬운 형태로 정리합니다.

---

# 34. 공급정보

대표 함수:

```python
_build_supply_information(...)
_extract_supply_table_rows(...)
_normalize_supply_housing_items_for_ui(...)
_extract_supply_location_from_housing_items(...)
_extract_supply_overview_location(...)
```

대표 구조:

```json
{
  "location": "...",
  "summary": "...",
  "housing_items": [
    {
      "complex_name": "...",
      "housing_type": "...",
      "supply_units": 1,
      "recruitment_people": 0
    }
  ]
}
```

---

## 34.1 공급표 Header Alias

공고마다 같은 의미를 다르게 적습니다.

예:

```text
모집인원수
모집 인원수
모집인원
모집 인원
```

모두:

```text
recruitment_people
```

로 매핑합니다.

반면:

```text
금회모집예비자수
모집할예비자수
```

는:

```text
recruitment_waitlist
```

입니다.

둘은 서로 다른 의미입니다.

---

## 34.2 숫자 0 처리

아래 값은 정상 값입니다.

```text
모집인원수 = 0
```

따라서 `0`을 빈 값으로 판단하면 안 됩니다.

예:

```text
공급호수 1호 · 모집인원 0명
```

처럼 보존합니다.

---

## 34.3 공급 위치

공급 위치는 단순 공고 지역과 다를 수 있습니다.

```text
announcement.region
= 경기도

실제 주택 위치
= 경기도 남양주시 화도읍 맷돌로91번길 7
```

Key Information은 가능한 경우 실제 공급표의 위치를 사용합니다.

공급 수량표에 주소가 없고 별도의:

```text
주택단지 개요
건설위치
```

표에만 주소가 있는 경우:

```python
_extract_supply_overview_location(...)
```

을 통해 실제 위치를 보완합니다.

---

# 35. 필요서류 / 발표 / 연락처

이 세 필드는 신청자격이나 공급표보다 비교적 단순하지만, 마찬가지로 Structure Section을 기반으로 찾습니다.

대표 Builder:

```python
_build_required_documents(...)
_build_winner_announcement(...)
_build_contact_information(...)
```

연락처의 경우 문서 전체 전화번호를 무조건 넣기보다 문의처 문맥을 우선합니다.

---

# 36. Document Worker와의 관계

문서처리 로직은 현재 Document Worker 안에서 실행됩니다.

단순 흐름:

```text
Backend
↓
Document Worker
↓
Parser
↓
Normalizer
↓
Structure
↓
Chunking
↓
Embedding
↓
Key Information
↓
Response
```

Document Worker는 **문서를 처리하는 역할**을 담당하며 DB Persistence 자체는 Backend 책임입니다.

따라서 Key Information 코드가 정상 동작하는지 확인할 때는:

```text
추출 결과
DB 저장 결과
Frontend 표시 결과
```

를 구분해야 합니다.

---

# 37. 문제를 찾을 때 단계별로 보는 방법

화면에 값이 잘못 보인다고 바로 Key Information을 수정하면 안 됩니다.

다음 순서로 확인합니다.

```text
원본 문서
↓
Parser JSON
↓
Normalized JSON
↓
Structured JSON
↓
Key Information
↓
DB/API
↓
Frontend
```

예:

```text
원문에는 값 있음
Parser에도 있음
Structure에도 있음
Key Information에도 있음
DB에도 있음
Frontend에서 없음
```

이면 문서처리 문제가 아니라 Frontend 표시 문제입니다.

반대로:

```text
Parser부터 값이 없음
```

이면 Parser 문제를 먼저 봐야 합니다.

---

# 38. 최근 실제 문제 사례

## 38.1 함양군 다자녀 매입임대

확인한 문제:

```text
공급 위치
모집인원수
0명 보존
다자녀 자격 상세조건
총자산
자동차가액
직계비속 정의
```

보완 결과:

```text
공급 위치
경남 함양군 서하면 송계앞길 7-2

공급 요약
공급호수 1호 · 모집인원 0명
```

---

## 38.2 남양주마석2단지 국민임대

확인한 문제:

```text
선정기준의 북한이탈주민 조건이 소득기준으로 오추출
예비신혼부부가 기본 신청대상처럼 오추출
20% 가산을 기본 소득기준 20%로 오인
성년자 원칙 문장 누락
주택단지 실제 주소 분리
```

보완 결과:

```text
공통 신청조건
무주택세대구성원

계층별 조건
성년자

소득/자산
월평균소득 70% 이하
1인가구 90%
2인가구 80%
총자산 34,500만원 이하
자동차가액 4,542만원 이하
```

---

# 39. 주요 함수만 빠르게 보는 코드 리뷰 순서

처음 코드를 리뷰한다면 아래 순서가 가장 이해하기 쉽습니다.

## 1. 형식 판별

```text
pipeline/parser/format_detector.py
```

```python
detect_actual_document_format()
_looks_like_hwpx_zip()
```

이 단계에서 실제 HWP/HWPX를 결정합니다.

---

## 2. HWP Parser

```text
pipeline/parser/hwp_parser.py
```

우선 볼 함수:

```python
parse_hwp()
parse_table()
find_nested_tables_in_hwp_cell()
extract_hwp_paragraph_text()
```

이 네 개를 보면:

```text
문서 읽기
문단 읽기
표 읽기
중첩표 읽기
```

흐름을 이해할 수 있습니다.

---

## 3. HWPX Parser

```text
pipeline/parser/hwpx_parser.py
```

우선 볼 부분:

```python
recover_table_item_numbers()
load_hwpx_xml_top_level_paragraphs()
```

그리고 HWP Parser와 동일하게 최종 공통 JSON 구조를 어떻게 만드는지 확인합니다.

---

## 4. Normalizer

```text
pipeline/normalizer/document_normalizer.py
```

우선 볼 부분:

```text
VERIFIED_PRIVATE_USE_MAP
SAFE_CHARACTER_REPLACEMENTS
NormalizationContext
```

여기서:

```text
어떤 문자를 바꾸는가
어떤 문자는 보존하는가
어떤 Warning을 남기는가
```

를 확인하면 됩니다.

---

## 5. Structure Step 1

```text
pipeline/structure/build_document_step1.py
```

주요 함수:

```python
parse_marker()
paragraph_heading_candidate()
semantic_heading_candidate()
table_heading_candidate()
is_layout_container()
```

핵심 질문:

```text
이 문장을 제목으로 볼 것인가?
몇 Level의 제목인가?
외곽 레이아웃 표인가 실제 데이터 표인가?
```

---

## 6. Structure Step 2

```text
pipeline/structure/build_domain_step2.py
```

주요 함수:

```python
normalize_title()
build_classification_sources()
```

핵심 질문:

```text
이 Section은 신청자격인가?
공급정보인가?
일정인가?
```

---

## 7. Structure Step 3

```text
pipeline/structure/build_table_step3.py
```

주요 함수:

```python
cell_range()
build_grid()
```

핵심 질문:

```text
병합표를 어떻게 Grid로 복구하는가?
Header와 Value가 어떻게 연결되는가?
```

---

## 8. Value Normalizer / Verification

```text
pipeline/structure/value_normalizer.py
pipeline/structure/verification.py
```

주요 함수:

```python
normalize_search_text()
verify_document()
```

핵심 질문:

```text
값을 검색 가능한 형태로 어떻게 정리하는가?
최종 구조가 안전한가?
```

---

## 9. Key Information

```text
pipeline/key_information_extractor.py
```

우선 볼 함수:

```python
extract_key_information()
_build_application_period()
_build_eligibility()
_build_supply_information()
_build_income_asset_criteria()
```

이후 특정 공고 문제를 볼 때 필요한 Helper만 따라가면 됩니다.

---

# 40. 각 단계가 실패했을 때 나타나는 문제

## Parser 문제

증상:

```text
원문에 있는 문단이 없음
표 자체가 없음
셀 위치가 잘못됨
중첩표가 사라짐
```

수정 위치:

```text
parser/
```

---

## Normalizer 문제

증상:

```text
특수문자 때문에 제목 인식 실패
같은 문자 표현이 서로 다르게 남음
PUA가 그대로 남음
```

수정 위치:

```text
normalizer/
```

---

## Structure 문제

증상:

```text
본문이 제목으로 잡힘
신청자격 Section이 다른 Section 아래로 들어감
Header-Value가 잘못 연결됨
병합 셀 값이 잘못 상속됨
```

수정 위치:

```text
structure/
```

---

## Key Information 문제

증상:

```text
Structure에는 값이 있는데 사용자 핵심정보에는 없음
선정기준을 신청자격으로 오인
소득/자산 값 오추출
공급정보 Alias 미지원
```

수정 위치:

```text
key_information_extractor.py
```

---

## Frontend 문제

증상:

```text
DB에는 값이 있는데 화면에서만 안 보임
값 우선순위 때문에 다른 값 표시
첫 detail이 잘림
0이 빈 값처럼 처리됨
```

이 경우 문서처리 코드를 수정하면 안 됩니다.

---

# 41. 문서처리 파트의 핵심 설계 원칙

전체 코드를 이해할 때 아래 원칙을 기억하면 됩니다.

### 1. 원문을 최대한 보존한다

Parser에서 의미를 과도하게 해석하지 않습니다.

### 2. 확실한 것만 자동 복원한다

PUA나 번호가 애매하면 임의 추측하지 않습니다.

### 3. 표현 정리와 의미 정리를 분리한다

```text
document_normalizer
→ 문자/표현

value_normalizer
→ 값/타입
```

### 4. 구조를 먼저 만들고 핵심정보를 뽑는다

Key Information은 원본 HWP를 바로 Regex로 긁는 단계가 아닙니다.

```text
원본
→ Parser
→ Normalizer
→ Structure
→ Key Information
```

### 5. 표는 문자열이 아니라 관계로 본다

```text
Header
→ Value
```

관계와 병합 정보를 보존합니다.

### 6. 애매하면 원본을 유지한다

잘못 추론해서 구조를 만드는 것보다 `warning` 또는 `skipped` 상태로 남기는 것이 안전합니다.

---

# 42. 최종 정리

문서처리 담당 파트는 단순히 HWP를 텍스트로 바꾸는 기능이 아닙니다.

전체 역할을 한 문장으로 정리하면:

> **HWP/HWPX 원문에서 문단·표·중첩표와 문서 계층을 최대한 보존해 구조화하고, 그 결과를 기반으로 RAG와 사용자 화면에서 사용할 수 있는 핵심정보를 만드는 파트입니다.**

단계별 역할은 다음과 같습니다.

```text
Format Detection
= 실제 문서 형식 확인

Parser
= 문단/표/중첩표를 원문 구조와 함께 추출

Normalizer
= HWP/HWPX 표현 차이와 특수문자를 공통 형태로 정리

Structure Step 1
= 제목과 본문 계층 생성

Structure Step 2
= Section 의미 분류 및 잘못된 계층 보정

Structure Step 3
= 병합표 Grid와 Header-Value 관계 복원

Value Normalizer
= 날짜/금액/면적/전화번호/백분율 등 값 정규화

Verification
= 구조 결과의 오류/경고 검증

Key Information
= 구조화 결과에서 사용자에게 필요한 7개 핵심정보 추출
```

처음 프로젝트를 보는 경우에는 다음 순서로 코드를 읽는 것을 권장합니다.

```text
format_detector.py
↓
hwp_parser.py / hwpx_parser.py
↓
document_normalizer.py
↓
run_structure.py
↓
build_document_step1.py
↓
build_domain_step2.py
↓
build_table_step3.py
↓
value_normalizer.py
↓
verification.py
↓
key_information_extractor.py
```

이 순서대로 보면 **원본 문서가 최종 핵심정보로 변환되는 전체 흐름**을 가장 쉽게 이해할 수 있습니다.

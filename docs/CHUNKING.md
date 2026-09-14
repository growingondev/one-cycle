# Chunking

> 기준 브랜치: `main`  
> 기준 구현: `document_worker/service.py`, `pipeline/chunking/`  
> 이 문서는 DDOK BOT 서비스에서 구조화된 HWP/HWPX 문서가 실제로 어떻게 Chunk로 변환되는지 설명한다.

---

## 1. 개요

Chunking은 Structure 단계에서 생성된 구조화 JSON을 **검색과 임베딩에 사용할 수 있는 의미 단위의 Chunk**로 변환하는 단계다.

DDOK BOT은 공공기관 공고문처럼 제목 계층과 표가 중요한 문서를 처리하기 때문에 단순히 일정 글자 수나 토큰 수만큼 자르는 방식 대신 **Structure-Aware Chunking**을 사용한다.

현재 전략명은 다음과 같다.

```text
hierarchical-structure-aware
```

핵심 원칙은 다음과 같다.

- 문서의 Section 계층을 유지한다.
- Paragraph와 Table을 서로 다른 방식으로 처리한다.
- Table의 Header-Value 관계를 유지한다.
- 구조화 단계에서 생성된 병합 값과 정규화 정보를 활용한다.
- 금액·면적 등의 단위가 다른 필드에 잘못 적용되지 않도록 검사한다.
- Chunk마다 원본 문서의 위치 정보를 유지한다.
- 표시, 검색, 임베딩 목적에 맞게 `content`, `search_text`, `embedding_text`를 각각 생성한다.

---

## 2. 실제 서비스에서의 위치

현재 서비스에서 Chunking은 **Document Worker의 문서 처리 Pipeline 안에서 실행된다.**

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
Embedding Service
  ↓
Persistence
```

Document Worker의 `document_worker/service.py`는 Structure 단계가 끝난 뒤 `_run_chunking()`을 호출한다.

실제 호출 관계는 다음과 같다.

```text
document_worker/service.py
  ↓
_run_chunking()
  ↓
pipeline/chunking/run_chunking.py
  ↓
StructureAwareChunker
  ↓
chunks.json
```

Document Worker는 `run_chunking.py`를 subprocess로 실행하면서 다음 값을 전달한다.

```text
--input
  Structure 최종 JSON

--output
  chunks.json

--announcement-id
  현재 공고 ID
```

따라서 `pipeline/chunking/run_chunking.py`는 현재 서비스의 **실제 Chunking 실행 진입점**이다.

---

## 3. 서비스 입력과 출력

### 입력

Document Worker가 Chunking에 전달하는 Structure 최종 결과:

```text
03_structured/{hwp|hwpx}/
└── step4-1_value_normalized.json
```

### 출력

```text
04_chunks/{hwp|hwpx}/
└── chunks.json
```

Document Worker는 Chunking subprocess가 정상 종료되었는지 확인한 뒤 `chunks.json`이 실제로 생성되었는지도 검사한다.

파일이 생성되지 않았거나 실행에 실패하면 Document Worker 단계에서 다음 오류로 처리한다.

```text
DOCUMENT_CHUNKING_FAILED
```

---

## 4. 주요 코드 구조

```text
pipeline/chunking/
├── __init__.py
├── config.py
├── models.py
├── validator.py
├── section_walker.py
├── tokenizer.py
├── text_builder.py
├── paragraph_chunker.py
├── table_chunker.py
├── chunker.py
└── run_chunking.py
```

| 파일 | 역할 |
|---|---|
| `run_chunking.py` | 서비스에서 실제 호출되는 Chunking 실행 진입점 |
| `chunker.py` | 전체 Chunking 흐름을 조율하는 Orchestrator |
| `config.py` | Chunk 크기와 전략 등 설정 관리 |
| `models.py` | Chunk 및 Source Metadata 모델 |
| `validator.py` | Structure JSON 입력 검증 |
| `section_walker.py` | Section / Children 계층 순회 |
| `paragraph_chunker.py` | Paragraph 그룹화 및 긴 문단 분할 |
| `table_chunker.py` | 구조화 Table을 Record 단위 Chunk로 변환 |
| `text_builder.py` | 표시·검색·임베딩용 텍스트 생성 |
| `tokenizer.py` | Token 수 계산 및 Overlap 처리 |

전체 동작의 중심 클래스는 다음이다.

```text
StructureAwareChunker
```

---

## 5. 전체 Chunking 흐름

```text
step4-1_value_normalized.json
  ↓
run_chunking.py
  ↓
StructureAwareChunker
  ↓
StructuredJsonValidator
  ↓
Intro 처리
  ↓
Sections 재귀 순회
  ↓
Contents 원본 순서 유지
  ↓
┌────────────────────┬────────────────────┐
│ Paragraph          │ Table              │
│                    │                    │
│ ParagraphChunker   │ TableChunker       │
└─────────┬──────────┴──────────┬─────────┘
          │                     │
          └──────────┬──────────┘
                     ↓
                 Chunk 생성
                     ↓
      content / search_text / embedding_text
                     ↓
            Metadata / Source 정보
                     ↓
             Quality Gate / Report
                     ↓
                 chunks.json
```

---

## 6. 입력 검증

Chunking을 시작하기 전에 `StructuredJsonValidator`가 Structure JSON의 기본 계약을 확인한다.

대표적으로 다음 정보를 검증한다.

```text
document
├── filename
└── format

intro

sections
├── section_id
├── level
├── title
├── contents
└── children
```

또한 다음과 같은 구조 문제도 확인한다.

- 중복 `section_id`
- 잘못된 Section 구조
- Paragraph 내용
- Table 구조
- 지원하지 않는 Content Type

지원하지 않는 Content Type은 전체 Chunking을 바로 중단하기보다 Warning으로 기록하고 건너뛸 수 있다.

---

## 7. Section 계층 유지

`section_walker.py`는 중첩된 Section을 재귀적으로 순회한다.

예를 들어 문서 구조가 다음과 같다면,

```text
공급정보
├── 공급대상
└── 임대조건
    └── 임대보증금
```

`임대보증금` 아래에서 생성되는 Chunk에는 다음과 같은 Section 경로가 유지된다.

```text
공급정보 > 임대조건 > 임대보증금
```

내부적으로는 다음과 같은 형태다.

```text
section_path = [
  "공급정보",
  "임대조건",
  "임대보증금"
]
```

이 정보는 이후 `content`, `search_text`, `embedding_text` 생성에 사용된다.

따라서 본문 내용이 비슷하더라도 **문서의 어느 항목에 속한 정보인지 함께 검색·임베딩할 수 있다.**

---

## 8. Paragraph Chunking

일반 문단은 `ParagraphChunker`가 처리한다.

연속된 Paragraph는 원본 순서를 유지하면서 하나의 Chunk로 묶는다.

기본 설정:

```text
target_tokens = 500
max_tokens    = 800
min_tokens    = 80
```

개념적으로:

```text
Paragraph 1
Paragraph 2
Paragraph 3
      ↓
Token 기준 그룹화
      ↓
Paragraph Group Chunk
```

Chunk가 `target_tokens`에 도달하면 하나의 그룹으로 확정하고, `max_tokens`를 넘지 않도록 제어한다.

---

## 9. 긴 Paragraph 처리

Paragraph 하나가 `max_tokens`보다 긴 경우 하나의 Chunk로 유지하지 않는다.

현재 분할 순서는 다음과 같다.

```text
긴 Paragraph
  ↓
문장 단위 분리
  ↓
그래도 너무 긴 문장
  ↓
단어 단위 분리
  ↓
그래도 너무 긴 단어
  ↓
문자 단위 분리
```

문장 경계는 일반 문장부호뿐 아니라 공공문서에서 자주 사용하는 목록 표현도 고려한다.

예:

```text
■
※
●
◆
1.
가.
```

이를 통해 최대한 자연스러운 문장 경계를 유지하면서 길이 제한을 맞춘다.

---

## 10. Paragraph Overlap

긴 Paragraph가 여러 Chunk로 나뉠 때 문맥이 완전히 끊어지는 것을 줄이기 위해 Overlap을 적용한다.

기본 설정:

```text
use_paragraph_overlap = True
overlap_tokens = 80
```

개념:

```text
Chunk 1
A B C D

Chunk 2
    C D E F
    └── 이전 Chunk의 일부
```

Table은 기본적으로 Overlap을 사용하지 않는다.

```text
use_table_overlap = False
```

---

## 11. 작은 마지막 Paragraph Chunk 병합

Paragraph 그룹의 마지막 Chunk가 너무 작을 경우 이전 Chunk와 합칠 수 있다.

조건:

```text
마지막 Chunk < min_tokens

AND

이전 Chunk + 마지막 Chunk <= max_tokens
```

조건을 만족하면 이전 Chunk에 병합하여 지나치게 작은 Chunk가 생성되는 것을 줄인다.

---

## 12. Table Chunking

공고문의 공급정보, 임대조건, 신청자격 등 핵심 정보는 Table에 많이 포함되어 있다.

따라서 Table은 Paragraph와 동일한 방식으로 자르지 않고 `TableChunker`에서 별도로 처리한다.

현재 분기 구조:

```text
structured + key_value
        ↓
Key-Value 방식

structured + row_records
        ↓
Row Record 방식

그 외
        ↓
Fallback 방식
```

즉 Structure 단계에서 이미 만들어진 Table 구조를 최대한 활용한다.

---

## 13. Key-Value Table

`layout == "key_value"`인 구조화 Table은 Key와 Value 관계를 유지한다.

예:

```text
단지명: A단지
소재지: 서울특별시
총 세대수: 500
```

작은 Key-Value Table은 전체를 하나의 Chunk로 유지한다.

기본 기준:

```text
small_key_value_table_tokens = 400
```

400 Token을 넘는 등 Table이 커지면 Record 단위로 나누어 처리한다.

---

## 14. Row Record Table

`layout == "row_records"`인 Table은 각 Record를 의미 단위로 처리한다.

예를 들어 Structure 결과가 다음 의미를 가진다면,

```text
주택형 | 공급세대수 | 임대보증금 | 월임대료
26A   | 58         | ...        | ...
29B   | 74         | ...        | ...
```

Chunking은 각 Record의 `header_path`와 `value`를 사용하여 다음과 같은 표현을 만든다.

```text
주택형: 26A
공급세대수: 58
임대보증금: ...
월임대료: ...
```

따라서 Table을 단순 문자열로 자르는 것이 아니라 **Header와 Value의 관계를 유지한 검색 가능한 표현으로 변환**한다.

---

## 15. 병합 셀 정보

Row Record에는 Structure 단계에서 생성된 `merged_values`가 존재할 수 있다.

Chunking은 이를 다시 병합 계산하지 않고 전달받은 구조를 사용한다.

```text
merged_values
  ↓
header / label + value
  ↓
Chunk 본문 및 검색 표현
```

즉 병합 셀 해석의 주 책임은 Structure 단계에 있고, Chunking은 그 결과를 유지하여 검색 가능한 형태로 변환한다.

---

## 16. Table Fallback

정상적인 `structured_table` 정보를 사용할 수 없는 경우 raw `cells` 기반 Fallback 처리를 한다.

단일 행·열 형태는 셀 내용을 하나의 Chunk로 유지할 수 있다.

여러 행이 있는 경우 Row별로 정렬하여 다음과 같은 형태로 만든다.

```text
값1 | 값2 | 값3
```

Fallback은 구조화된 `key_value` 또는 `row_records`보다 의미 정보가 적기 때문에 정상적인 Structured Table 결과를 우선 사용한다.

---

## 17. Table 단위 처리

공고문의 Table에는 다음과 같은 단위가 자주 등장한다.

```text
원
천원
만원
억원
㎡
m²
m2
%
```

Chunking은 주변에 단위가 존재한다는 이유만으로 모든 숫자에 같은 단위를 붙이지 않는다.

Header의 의미를 확인하여 대표적으로 다음 Semantic Type을 구분한다.

```text
money
area
count
duration
identifier
unknown
```

예:

```text
임대보증금   → money
주거전용면적 → area
모집호수     → count
거주기간     → duration
주택형       → identifier
```

---

## 18. 단위 적용 우선순위

단위는 대략 다음 순서로 판단한다.

```text
1. Value 자체에 명시된 단위
2. Normalization 결과에 있는 단위
3. Header에 명시된 단위
4. Table 전체 또는 직전 단위 선언 Paragraph
```

단, Table 전체나 이전 Paragraph에서 상속되는 단위는 약한 근거로 취급한다.

Header의 의미와 단위 종류가 맞을 때만 적용한다.

예를 들어 Table 주변에 `(㎡)`가 있더라도:

```text
모집호수: 58
```

을 다음처럼 만들지 않는다.

```text
모집호수: 58㎡
```

Count, Duration, Identifier 성격의 Field에는 금액·면적 단위를 적용하지 않는다.

---

## 19. 직전 Paragraph의 단위 상속

Table 바로 앞 Paragraph 전체가 단위 선언인 경우 해당 단위를 Table 처리에 전달할 수 있다.

예:

```text
[단위: 천원]
```

`StructureAwareChunker`는 Table을 처리하기 전에 직전 Paragraph가 단위만 선언하는 문장인지 확인한다.

확인된 단위는 `inherited_unit`으로 `TableChunker`에 전달된다.

단, 실제 Value에 적용할 때는 Header 의미와의 호환성을 다시 확인한다.

---

## 20. Entity 유지

Structure / Normalization 단계에서 Value에 Entity 정보가 존재하면 Chunk에도 유지한다.

예:

```text
numeric_value
normalized_value
won_value
unit
```

필요한 경우 Chunking 단계에서 신뢰 가능한 단위 정보를 이용해 Entity를 보완할 수도 있다.

이를 통해 검색 과정에서 원문 표현뿐 아니라 정규화된 숫자와 단위 정보도 활용할 수 있다.

---

## 21. Chunk의 세 가지 텍스트

하나의 Chunk에는 목적이 다른 세 가지 텍스트가 존재한다.

```text
content
search_text
embedding_text
```

### `content`

LLM Context와 Evidence로 사용하기 적합한 본문 표현이다.

Section 경로를 포함할 수 있다.

예:

```text
[임대조건 > 임대보증금]

주택형: 26A
임대보증금: ...
월임대료: ...
```

### `search_text`

Keyword Search 등 검색 Recall을 높이기 위한 표현이다.

다음 정보를 조합한다.

```text
section_path
normalized_title
search_title
body_search_text
domain.category
domain.topic
정규화된 검색 정보
```

중복되는 문자열은 제거하여 조합한다.

### `embedding_text`

Dense Embedding 모델에 전달할 텍스트다.

기본 구조:

```text
Section 경로
+
본문
```

예:

```text
임대조건 > 임대보증금
주택형: 26A
임대보증금: ...
월임대료: ...
```

즉 Chunking 단계에서 **표시용, 검색용, 임베딩용 텍스트를 목적에 따라 분리**한다.

---

## 22. Chunk Metadata

생성되는 Chunk에는 본문뿐 아니라 Retrieval과 원본 추적에 필요한 Metadata가 포함된다.

대표 구조:

```text
Chunk
├── chunk_id
├── chunk_order
├── chunk_type
│
├── document_id
├── announcement_id
├── source_filename
├── source_format
│
├── section_id
├── section_level
├── section_path
├── title
├── normalized_title
├── search_title
│
├── content
├── search_text
├── embedding_text
│
├── domain
├── source
├── entities
│
├── token_count
├── char_count
└── chunking
```

---

## 23. Source Metadata

`source`에는 Chunk가 원본 문서의 어디에서 만들어졌는지 추적할 수 있는 정보가 들어간다.

대표 정보:

```text
content_type
paragraph_indexes
table_index
record_index
row_index
row_kind
origin_paths
object_path
```

따라서 Retrieval 결과에서 특정 Chunk가 선택되었을 때 원본의 Section, Paragraph 또는 Table Record 위치를 추적할 수 있다.

---

## 24. Chunk Type

현재 대표 Chunk Type은 다음과 같다.

```text
intro
paragraph_group
paragraph_split
table_record
table_fallback
```

### `intro`

문서 Intro 영역에서 생성된 Chunk.

### `paragraph_group`

여러 연속 Paragraph를 묶어 생성한 Chunk.

### `paragraph_split`

하나의 긴 Paragraph가 여러 부분으로 나뉜 경우.

### `table_record`

정상적으로 구조화된 Table Record에서 생성된 Chunk.

### `table_fallback`

Structured Table을 사용하지 못하고 Fallback 방식으로 생성한 Chunk.

보다 세부적인 처리 방법은 `chunking.strategy`에 저장된다.

예:

```text
paragraph
paragraph_group
key_value_group
key_value_record
row_record
table_fallback_whole
table_fallback_row
```

---

## 25. Chunk ID와 순서

Chunk ID는 Document ID, Section, 원본 위치를 기반으로 생성된다.

Paragraph 예:

```text
{document_id}_{section_id}_para_0001
```

Table 예:

```text
{document_id}_{section_id}_tbl_0003_rec_0001
```

하나의 내용이 여러 Part로 나뉜 경우:

```text
_p01
_p02
```

등의 정보가 추가될 수 있다.

중복 ID가 발생하면 추가 Suffix를 붙여 고유성을 유지한다.

`chunk_order`는 생성 순서대로 1부터 증가한다.

---

## 26. Token 계산

기본 Token Counter는 다음이다.

```text
RegexTokenCounter
```

한국어 음절, 영문 단어, 숫자, 문장부호 등을 이용하여 Token 수를 근사한다.

따라서 기본 설정:

```text
500 / 800 / 80
```

은 BGE-M3의 실제 Tokenizer 기준 Token 수와 반드시 동일한 값은 아니다.

필요한 경우 `tokenizer_name_or_path`를 지정해 Hugging Face Tokenizer 기반 Counter를 사용할 수 있다.

---

## 27. Section 경로를 고려한 Token Budget

`embedding_text`에는 본문뿐 아니라 Section 경로도 들어간다.

따라서 Chunker는 Section Heading이 차지하는 Token을 고려해 실제 Body가 사용할 수 있는 최대 크기를 계산한다.

개념적으로:

```text
max body tokens
=
max_tokens
-
section heading reserve
```

이를 통해 Section 경로가 추가된 최종 `embedding_text`도 최대 길이를 넘지 않도록 제어한다.

---

## 28. Quality Gate

Chunk 생성이 끝나면 Report를 생성하여 품질 상태를 확인한다.

주요 검사 항목:

```text
max token 초과
빈 embedding_text
중복 chunk_id
중복 content
source reference 누락
단위 오염 의심
```

Report의 대표 구조:

```text
report
├── total_chunks
├── chunk_types
├── token_stats
├── quality_gate
├── warnings
└── source_value_normalization_warnings
```

`quality_gate.pass`는 주요 품질 위반이 없는지를 나타낸다.

---

## 29. 현재 설정

`pipeline/chunking/config.py`의 기본값:

| 설정 | 기본값 | 의미 |
|---|---:|---|
| `strategy` | `hierarchical-structure-aware` | Chunking 전략 |
| `schema_version` | `chunk-v1` | Chunk Schema |
| `target_tokens` | 500 | 일반적인 목표 Chunk 크기 |
| `max_tokens` | 800 | 최대 Chunk 크기 |
| `min_tokens` | 80 | 작은 마지막 Chunk 병합 기준 |
| `overlap_tokens` | 80 | Paragraph 분할 시 Overlap |
| `small_key_value_table_tokens` | 400 | 작은 Key-Value Table 통합 기준 |
| `include_section_path_in_content` | `True` | Content에 Section 경로 포함 |
| `include_section_path_in_search_text` | `True` | Search Text에 Section 경로 포함 |
| `include_domain_in_search_text` | `True` | Search Text에 Domain 포함 |
| `use_paragraph_overlap` | `True` | Paragraph Overlap 사용 |
| `use_table_overlap` | `False` | Table Overlap 기본 미사용 |

현재 Chunking 결과에는 구현 버전도 기록된다.

```text
implementation_version
=
generalized-unit-semantic-v5
```

---

## 30. `run_chunking.py`의 두 가지 역할

`run_chunking.py`에는 서비스 실행 외에도 독립 실행을 위한 기능이 존재한다.

### 실제 서비스에서 사용하는 방식

Document Worker가 명시적으로 다음 인자를 전달한다.

```text
--input
--output
--announcement-id
```

즉 하나의 문서에 대해 Structure 결과를 Chunking한다.

### 독립 실행 기능

개발·검증 시 인자를 생략하면 프로젝트의 다음 경로를 자동 탐색할 수 있다.

```text
outputs/announcement_*/03_structured/{hwp|hwpx}/
```

입력 우선순위:

```text
1. step4-1_value_normalized.json
2. step3-3_structured_tables.json
```

이 자동 탐색 기능은 `run_chunking.py`에 존재하지만, **현재 서비스의 Document Worker 호출 방식은 명시적 `--input / --output / --announcement-id` 방식**이다.

---

## 31. 왜 Structure-Aware Chunking을 사용하는가

공공기관 공고문은 일반 자연어 문서와 달리 다음 특징이 강하다.

```text
제목 / 소제목 계층
긴 조건 설명
다수의 표
주택형별 수치
대상자별 조건
금액 / 면적 / 기간 단위
```

단순 길이 기준으로만 자르면 다음과 같은 문제가 발생할 수 있다.

```text
제목과 본문 분리
Table Header와 Value 분리
서로 다른 Row의 값 혼합
단위 정보 손실
원본 위치 추적 어려움
```

현재 Chunking은 앞 단계에서 이미 분석한 문서 구조를 활용하여 이러한 정보 손실을 줄이는 것을 목표로 한다.

Semantic Chunking처럼 Embedding 유사도를 이용해 새로운 경계를 찾는 방식이 아니라, **문서에 존재하는 명시적인 구조를 우선적으로 이용해 Chunk 경계를 결정하는 방식**이다.

---

## 32. 서비스 기준 최종 흐름

```text
Document Worker
      ↓
Structure
      ↓
step4-1_value_normalized.json
      ↓
_run_chunking()
      ↓
run_chunking.py
      ↓
StructureAwareChunker
      ↓
┌─────────────────────────────┐
│ Section 계층 유지           │
│ Paragraph Chunking          │
│ Table Record Chunking       │
│ Header-Value 유지           │
│ 단위 / Entity 처리          │
│ Source Metadata 유지        │
└──────────────┬──────────────┘
               ↓
       content
       search_text
       embedding_text
               ↓
          chunks.json
               ↓
        Document Worker
               ↓
       Embedding Service
```

---

## 33. 핵심 정리

현재 DDOK BOT의 Chunking은 다음과 같이 정리할 수 있다.

```text
방식
= Structure-Aware Chunking

실제 서비스 실행 주체
= Document Worker

실제 실행 진입점
= pipeline/chunking/run_chunking.py

핵심 구현
= StructureAwareChunker

입력
= step4-1_value_normalized.json

출력
= chunks.json

Paragraph
= Token 기준 그룹화 + 긴 문단 분리 + Overlap

Table
= Key-Value / Row Record / Fallback

검색·임베딩용 출력
= content / search_text / embedding_text
```

Chunking의 핵심 목적은 **구조화 단계에서 확보한 문서 구조와 표의 의미 관계를 최대한 유지하면서, 이후 Embedding과 Retrieval이 사용할 수 있는 검색 단위로 변환하는 것**이다.

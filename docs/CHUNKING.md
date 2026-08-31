# 청킹(Chunking) 파트 문서

## 1. 청킹 파트 역할

청킹 단계는 앞 단계에서 생성된 **구조화 HWP/HWPX JSON**을 입력으로 받아,
이후 임베딩과 검색에 사용할 수 있는 작은 단위의 청크로 변환하는
단계이다.

단순히 일정 글자 수로 문서를 자르는 방식이 아니라 문서의

-   section 계층
-   문단 구조
-   표 구조
-   표의 단위 정보
-   정규화된 값
-   공고 ID
-   원본 위치 정보

를 최대한 유지하는 **Structure-Aware Chunking 방식**을 사용한다.

현재 기본 전략명은 `hierarchical-structure-aware`이고, 기본 설정은
target 500 / max 800 / min 80 / overlap 80 토큰이다.

------------------------------------------------------------------------

## 2. 전체 파이프라인에서의 위치

``` text
HWP / HWPX
    ↓
Parsing
    ↓
Normalization / Structure Analysis
    ↓
03_structured JSON
    ↓
[Chunking] ← 현재 파트
    ↓
04_chunks/{hwp|hwpx}/chunks.json
    ↓
Embedding
    ↓
Vector DB / Retrieval
```

`run_chunking.py`는 기본 실행 시

``` text
outputs/announcement_*/03_structured/{hwp,hwpx}/
```

에서 최종 구조화 JSON을 자동 탐색하고 결과를

``` text
outputs/announcement_*/04_chunks/{hwp,hwpx}/chunks.json
```

으로 저장한다. 단일 파일 실행과 폴더 일괄 실행도 지원한다.

따라서 현재 청킹은 네트워크 API로 호출되는 서비스가 아니라 **같은
프로젝트 내부 Python 코드 + 파일 입출력 방식으로 동작하는 파이프라인
단계**이다.

------------------------------------------------------------------------

## 3. 청킹 전체 실행 흐름

실제 실행 흐름은 다음과 같다.

``` text
run_chunking.py
        ↓
CLI 인자 분석
        ↓
ChunkingConfig 생성
        ↓
StructureAwareChunker 생성
        ↓
입력 구조화 JSON 탐색
        ↓
chunk_one_file()
        ↓
StructureAwareChunker.chunk_file()
        ↓
JSON 로딩
        ↓
chunk_document()
        ↓
StructuredJsonValidator
        ↓
intro 처리
        ↓
section / children 재귀 순회
        ↓
content type 확인
        ├─ paragraph → ParagraphChunker
        │
        └─ table → TableChunker
        ↓
content 생성
search_text 생성
embedding_text 생성
        ↓
Chunk 객체 생성
        ↓
청크 결과 검증
        ↓
chunks.json 저장
        ↓
Embedding 단계
```

`chunk_one_file()`에서도 이 흐름을 직접 설명하고 있으며, 내부에서 입력
검증 → intro → section 재귀 순회 → 문단/표 청킹 → 검색·임베딩 텍스트
생성 → 결과 검증 및 저장 순서로 동작한다.

------------------------------------------------------------------------

## 4. 주요 파일 구조

``` text
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

각 파일은 기능별로 분리되어 있으며 `StructureAwareChunker`가 이들을
조합하여 전체 청킹 과정을 제어한다. `__init__.py`에서는 외부에서 주로
사용할 `StructureAwareChunker`와 `ChunkingConfig`를 패키지 인터페이스로
노출한다.

------------------------------------------------------------------------

## 5. 파일별 역할

### `run_chunking.py`

#### 역할

청킹 파이프라인의 **실행 진입점**이다.

사용자가 직접 실행하거나 상위 `run_pipeline.py`에서 호출할 수 있다.

주요 역할:

-   CLI 인자 처리
-   ChunkingConfig 생성
-   구조화 JSON 탐색
-   단일 파일 청킹
-   폴더 일괄 청킹
-   전체 outputs 자동 청킹
-   결과 검증
-   chunks.json 저장
-   에러 기록

기본 실행 시 `announcement_*` 폴더들을 탐색하고 HWP/HWPX 각각의 구조화
결과를 찾아 대응하는 `04_chunks` 경로를 생성한다.

#### 주요 함수

`main()`

청킹 프로그램의 최상위 실행 함수이다.

``` text
build_parser()
    ↓
build_config()
    ↓
StructureAwareChunker()
    ↓
실행 모드 판단
    ├─ 기본 outputs 전체 처리
    ├─ 단일 JSON
    └─ JSON 폴더 일괄처리
```

실제 `main()`은 입력 인자가 없으면 프로젝트의 표준 outputs를 전체
처리하고, 파일이면 `chunk_one_file()`, 디렉터리면 `chunk_directory()`를
실행한다.

#### 다른 파트와의 중요한 연결

``` python
from backend.app.services.error_log_service import record_error
```

청킹 실패를 Backend 공통 ErrorLog에 기록하기 위해 **Backend 코드를
Python import 방식으로 직접 호출하고 있다.**

------------------------------------------------------------------------

## 6. `chunker.py`

### 역할

청킹 파트의 **핵심 Orchestrator**이다.

문단이나 표를 직접 모두 처리하는 것이 아니라 여러 모듈을 조합하여 전체
청킹 흐름을 제어한다.

초기화할 때 다음 객체들을 생성한다.

``` text
StructuredJsonValidator
ParagraphChunker
TableChunker
TokenCounter
```

즉 `StructureAwareChunker`가 청킹 전체의 중심 객체이다.

### `chunk_file()`

입력 JSON 파일을 읽고 Python dict로 변환한 뒤 `chunk_document()`를
호출한다.

``` text
JSON file
 ↓
json.load()
 ↓
chunk_document()
```

### `chunk_document()`

청킹의 핵심 함수다.

처리 순서:

``` text
StructuredJsonValidator.validate()
        ↓
입력 구조 검증
        ↓
document_id 생성
announcement_id 설정
        ↓
_process_intro()
        ↓
_process_sections()
        ↓
Chunk 리스트 생성
        ↓
report 생성
```

출력에는

-   document 정보
-   chunking 설정
-   chunks
-   report

가 포함된다.

------------------------------------------------------------------------

## 7. 문서 계층 처리

### `section_walker.py`

중첩된 section 구조를 재귀적으로 순회한다.

예를 들어 구조화 JSON이

``` text
공급정보
 ├─ 공급대상
 └─ 공급금액
     └─ 납부일정
```

처럼 되어 있으면 각 section의 경로를 유지한다.

``` text
["공급정보"]
["공급정보", "공급대상"]
["공급정보", "공급금액"]
["공급정보", "공급금액", "납부일정"]
```

형태의 `section_path`를 생성한다.

`walk_sections()`는 현재 section을 반환한 후 children을 재귀적으로 다시
순회한다.

이 정보는 이후 검색·임베딩 텍스트에 포함된다.

------------------------------------------------------------------------

## 8. 문단 청킹

### `paragraph_chunker.py`

일반 본문 문단을 토큰 기준으로 나눈다.

처리 흐름은 다음과 같다.

``` text
paragraph 목록
      ↓
각 문단 토큰 확인
      ↓
max_tokens 이하
      ↓
그대로 사용

max_tokens 초과
      ↓
문장 기준 분리
      ↓
그래도 너무 길면 단어 기준 분리
      ↓
그래도 너무 길면 문자 단위 분리
```

그 다음 여러 작은 문단을 다시 묶어서 `target_tokens`에 근접하도록
구성한다.

### 너무 긴 문단 처리

먼저 한국어 문장 경계를 기준으로 나눈다.

그 후에도 최대 토큰을 초과하는 경우:

``` text
문장
 ↓
단어
 ↓
문자
```

순서로 더 작은 단위까지 분리한다.

### Overlap

문단이 여러 청크로 분리되면 이전 청크의 끝부분을 다음 청크에 일부
포함한다.

기본값:

``` text
overlap_tokens = 80
```

예:

``` text
Chunk 1
AAAAAAAA BBBBBBBB CCCCCCCC

Chunk 2
           CCCCCCCC DDDDDDDD EEEEEEEE
           └ overlap
```

이를 통해 청크 경계에서 문맥이 완전히 끊기는 것을 줄인다. 실제
코드에서는 `tail_by_tokens()`로 이전 청크 뒤쪽을 가져온다.

------------------------------------------------------------------------

## 9. 표 청킹

### `table_chunker.py`

LH 공고문의 중요한 정보는 표에 많이 존재하기 때문에 표는 일반 문단과
별도로 처리한다.

먼저 구조화 결과를 보고 표를 세 가지 방식으로 분기한다.

``` text
structured + key_value
        ↓
Key-Value 방식

structured + row_records
        ↓
행 레코드 방식

그 외
        ↓
Fallback 방식
```

### Key-Value 표

예:

``` text
단지명: A단지
위치: 서울특별시
총 세대수: 500
```

작은 표라면 하나의 청크로 유지하고, 크면 레코드 단위로 분리한다.

`small_key_value_table_tokens` 기본값은 400이다.

### Row Record 표

예:

``` text
주택형 | 세대수 | 분양가
59A   | 100   | 500,000
84A   | 200   | 700,000
```

각 행을 하나의 의미 있는 record로 취급한다.

따라서

``` text
주택형: 59A
세대수: 100
분양가: 500,000
```

형태처럼 검색 가능한 텍스트 표현으로 변환할 수 있다.

### 표 단위 보존

표에서는 `원`, `천원`, `만원`, `㎡`, `%` 등의 단위가 중요하기 때문에
별도의 단위 해석 로직이 존재한다.

예를 들어

``` text
[단위: 천원]

계약금 | 50,000
```

이라면 검색용 표현에서는

``` text
계약금: 50,000천원
```

처럼 단위를 보존하려고 한다.

특히 단순히 주변 단위를 무조건 적용하지 않고 `세대수`, `면적`, `가격`,
`기간` 등의 필드 의미를 분석하여 잘못된 단위가 들어가는 것을 방지한다.

------------------------------------------------------------------------

## 10. 텍스트 생성

### `text_builder.py`

하나의 청크에서 목적에 따라 서로 다른 텍스트를 만든다.

#### `content`

사용자에게 근거로 보여주기 좋은 본문 표현이다.

``` text
[공급정보 > 공급금액]

계약금: 50,000천원
잔금: 150,000천원
```

section path를 본문 앞에 포함할 수 있다.

#### `search_text`

검색 Recall을 높이기 위한 텍스트이다.

여기에

-   section path
-   normalized title
-   search title
-   body search text
-   domain

등을 조합한다.

#### `embedding_text`

실제 임베딩 단계에 전달할 텍스트이다.

기본적으로

``` text
section 경로
+
본문
```

형식이다.

즉 하나의 Chunk가 단순 문자열 하나가 아니라 **검색/표시/임베딩 목적에
맞는 여러 텍스트 표현을 가진다.**

------------------------------------------------------------------------

## 11. Tokenizer

### `tokenizer.py`

청크 길이를 판단하는 역할을 한다.

공통 인터페이스는 다음 두 기능이다.

``` text
count(text)
tail_by_tokens(text, token_count)
```

현재 tokenizer를 지정하지 않으면 `RegexTokenCounter`를 사용한다.

이는 한국어 음절, 영문 단어, 숫자, 문장부호 등을 기준으로 토큰 수를 근사
계산한다. 정확한 임베딩 모델 tokenizer가 확정되기 전에도 청킹 테스트를
할 수 있도록 만든 방식이다.

Tokenizer 경로를 지정하면 Hugging Face `AutoTokenizer`를 사용할 수도
있다.

------------------------------------------------------------------------

## 12. 입력 검증

### `validator.py`

청킹 시작 전에 구조화 JSON의 형식이 예상 계약을 만족하는지 검사한다.

예를 들어 다음을 확인한다.

``` text
document 존재 여부
document.filename
document.format
intro가 list인지
sections가 list인지
section_id 존재 여부
section level
section title
contents
children
paragraph.text
table.cells
structured_table
```

필수 구조가 잘못되면 error가 발생하고 청킹을 중단한다.

반면 `structured_table`이 없는 것처럼 처리가 가능하지만 품질에 영향을 줄
수 있는 경우에는 Warning으로 남긴다.

------------------------------------------------------------------------

## 13. Chunk 데이터 구조

### `models.py`

최종적으로 각각의 청크는 `Chunk` dataclass로 표현된다.

주요 정보:

``` text
chunk_id
chunk_order
chunk_type

document_id
announcement_id
source_filename
source_format

section_id
section_level
section_path
title
normalized_title
search_title

content
search_text
embedding_text

domain
source
entities

token_count
char_count
chunking
```

특히 `announcement_id`가 청크 자체에 저장되므로 이후 Retrieval에서
**선택한 공고에 대한 데이터만 검색하는 필터의 기반 정보**로 사용할 수
있다.

------------------------------------------------------------------------

## 14. Source 추적 정보

`ChunkSource`에는 청크가 원본 문서의 어디에서 왔는지를 저장한다.

문단이라면:

``` text
paragraph_indexes
origin_paths
```

표라면:

``` text
table_index
record_index
row_index
row_kind
object_path
```

등을 저장한다.

따라서 검색 결과가 나왔을 때 원본의 어느 문단/표에서 만들어진 청크인지
추적할 수 있다.

------------------------------------------------------------------------

## 15. 입력과 출력

### 입력

``` text
03_structured/{hwp|hwpx}/
    step4-1_value_normalized.json
```

우선 사용한다.

없으면 이전 구조와의 호환을 위해

``` text
step3-3_structured_tables.json
```

을 사용할 수 있다.

### 출력

``` text
04_chunks/{hwp|hwpx}/chunks.json
```

------------------------------------------------------------------------

## 16. 다른 파트와의 연결

현재 청킹 코드에서 확인되는 연결은 다음과 같다.

  ---------------------------------------------------------------------------------------
  호출하는 쪽               호출받는 쪽               방식              목적
  ------------------------- ------------------------- ----------------- -----------------
  구조화 단계               Chunking                  파일 I/O          구조화 JSON 전달

  `run_chunking.py`         `StructureAwareChunker`   Python import     청킹 실행

  `StructureAwareChunker`   Validator                 Python import     입력 검증

  `StructureAwareChunker`   ParagraphChunker          Python import     문단 처리

  `StructureAwareChunker`   TableChunker              Python import     표 처리

  `StructureAwareChunker`   Tokenizer                 Python import     토큰 계산

  Chunking                  Embedding                 파일 I/O          `chunks.json`
                                                                        전달

  `run_chunking.py`         Backend ErrorLog Service  **Python import** 청킹 오류 저장
  ---------------------------------------------------------------------------------------

여기에서 중요한 것은 **청킹 → 임베딩은 현재 API 통신이 아니라 파일을
매개로 연결**되고 있다는 점이다.

그리고 청킹 자체에서 직접 확인되는 Backend 의존성은

``` python
from backend.app.services.error_log_service import record_error
```

이다.

------------------------------------------------------------------------

## 17. 현재 MVP에서의 청킹 아키텍처

``` text
03_structured JSON
        │
        │ File I/O
        ▼
run_chunking.py
        │
        │ Python import
        ▼
StructureAwareChunker
        │
        ├──── Validator
        │
        ├──── SectionWalker
        │
        ├──── ParagraphChunker
        │
        ├──── TableChunker
        │
        ├──── TokenCounter
        │
        └──── TextBuilder
        │
        ▼
Chunk[]
        │
        ▼
chunks.json
        │
        │ File I/O
        ▼
Embedding

예외 발생
    │
    │ Python import
    ▼
Backend ErrorLog Service
```

------------------------------------------------------------------------

## 18. Docker 분리 시 확인해야 할 부분

현재 청킹 내부 모듈끼리의 `import`는 문제가 아니다.

예를 들어

``` python
from .paragraph_chunker import ParagraphChunker
```

처럼 **하나의 청킹 서비스 내부에서 사용하는 import**는 Docker로 나눈다고
해서 API로 바꿀 필요가 없다.

반면 다음은 서비스 경계를 넘을 가능성이 있기 때문에 확인이 필요하다.

``` python
from backend.app.services.error_log_service import record_error
```

현재는 Chunking 코드와 Backend 코드가 같은 Python 환경과 프로젝트 파일
시스템에 있기 때문에 직접 import할 수 있다.

하지만 향후

``` text
backend container
chunking/rag container
```

로 완전히 분리한다면 RAG 컨테이너에서 Backend 내부 Python 모듈을 직접
import하는 구조는 서비스 독립성이 떨어진다.

따라서 향후 확인 대상이다.

``` text
[현재]

Chunking
    ↓ Python import
Backend ErrorLog

[Docker 분리 검토]

Chunking
    ↓ HTTP API 또는 별도 로깅 구조
Backend
```

단, 현재 단계에서는 수정하지 않고 **AS-IS 의존성으로 기록한다.**

------------------------------------------------------------------------

## 19. 이 파트를 처음 보는 팀원이 반드시 알아야 할 것

청킹은 단순 문자열 분할 기능이 아니다.

이 프로젝트에서는 LH 공고문의 구조를 보존하기 위해

``` text
section 계층
+
paragraph 의미 단위
+
table record
+
단위 정보
+
정규화 값
+
공고 ID
```

를 최대한 보존하면서 검색과 임베딩에 적합한 데이터로 변환한다.

따라서 핵심 역할을 한 문장으로 정리하면 다음과 같다.

> **구조화된 공고문 JSON을 문서 구조와 표의 의미를 최대한 유지한 채
> 검색·임베딩 가능한 Chunk 데이터로 변환하는 단계이다.**

청킹 결과인 `chunks.json`이 다음 임베딩 단계의 입력이 되므로, 이
단계에서 생성되는 `announcement_id`, `embedding_text`, `search_text`,
`section_path`, `source`, `entities` 등의 메타데이터가 이후 RAG 검색
품질과 공고별 검색 분리에 직접 연결된다.

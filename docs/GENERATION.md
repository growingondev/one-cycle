# AI/RAG 코드리뷰 - Generation

## 1. Generation 개요

### 1.1 역할

Generation은 Retrieval 결과를 LLM이 사용할 근거 문맥으로 변환하고,
System Prompt와 사용자 질문을 조합한 뒤 **llama.cpp 서버를 HTTP로
호출하여 최종 답변을 생성하는 단계**이다.

현재 코드의 전체 흐름은 다음과 같다.

``` text
Retrieval Results
        ↓
SourceContext 생성
        ↓
Context 구성
        ↓
System/User Prompt 생성
        ↓
llama.cpp HTTP POST
        ↓
LLM 응답 추출
        ↓
답변 후처리
        ↓
답변 검증
        ↓
필요 시 1회 재생성
        ↓
GeneratedAnswer
```

Generation 내부 모듈들은 Python import로 연결되지만, **Generation →
llama.cpp는 Python import가 아니라 HTTP API 호출**이다.

### 1.2 주요 파일

``` text
rag/generation/
├─ __init__.py
├─ config.py
├─ context_builder.py
├─ generator.py
├─ llm_client.py
├─ models.py
└─ prompt_builder.py
```

  파일                   역할
  ---------------------- ----------------------------------
  `config.py`            llama.cpp 및 Generation 설정
  `context_builder.py`   Retrieval 결과 → `SourceContext`
  `prompt_builder.py`    System/User Prompt 구성
  `llm_client.py`        llama.cpp HTTP 호출
  `generator.py`         전체 Generation 실행 조율
  `models.py`            Generation 데이터 모델
  `__init__.py`          Generation 외부 인터페이스

------------------------------------------------------------------------

# 2. Generation 입력 및 Retrieval 연결

## 2.1 입력 데이터

Generation의 외부 진입점은:

``` text
generate_answer()
```

이다.

입력은 다음과 같다.

``` text
query
announcement_directory
document_format
retrieval_results
config
```

따라서 Generation은 Chunk나 Embedding 파일을 직접 읽지 않는다.

``` text
Retrieval
    ↓
SearchResult[] 등 Python 객체
    ↓
Generation
```

## 2.2 Retrieval 결과 처리

`context_builder.py`의 `_unwrap_retrieval_result()`는 전달받은 Retrieval
결과를 내부에서 사용할 형태로 맞춘다.

현재 문서에서 확인되는 지원 형태는:

``` text
현재 SearchResult

또는

기존 RetrievalResult
```

이다.

현재 `SearchResult`에서는 `fusion_score`, `fusion_rank`를 우선 사용하고
필요한 경우 `vector_score`, `vector_rank`를 사용한다.

즉 Retrieval과 Generation 사이의 현재 연결은 파일 I/O가 아니라 **Python
객체 전달**이다.

------------------------------------------------------------------------

# 3. Context 구성

## 3.1 `context_builder.py`

Retrieval 결과를 LLM Prompt에 사용할 `SourceContext`로 변환한다.

``` text
Retrieval Result[]
        ↓
결과 형식 정규화
        ↓
Top-K 선택
        ↓
Chunk Content 추출
        ↓
길이 제한
        ↓
SourceContext[]
```

## 3.2 사용할 근거 개수

모든 Retrieval 결과를 Prompt에 넣지는 않는다.

현재 기본값:

``` text
context_top_k = 5
```

따라서 예를 들어 Retrieval에서 20개가 반환되어도 기본적으로 상위 5개를
Generation 근거로 사용한다.

``` text
Retrieval 20개
     ↓
Top 5
     ↓
Generation Context
```

## 3.3 Context 길이 제한

현재 Context에 사용할 총 문자 제한 기본값은:

``` text
6000
```

이다.

선택한 Chunk를 순서대로 추가하며 허용 범위를 초과하면 내용을 잘라내고:

``` text
[이하 내용은 프롬프트 길이 제한으로 생략]
```

문구를 추가한다.

## 3.4 `SourceContext`

하나의 근거는 다음 구조로 관리된다.

``` text
SourceContext
├─ source_number
├─ chunk_id
├─ announcement_id
├─ document_id
├─ document_format
├─ section_path
├─ title
├─ content
├─ reranker_score
└─ reranker_rank
```

현재 필드 이름에는 `reranker_score`, `reranker_rank`가 남아 있지만, 현재
Generation 코드에서는 Hybrid Search의 Fusion Score/Rank도 이 호환 필드를
통해 처리할 수 있도록 되어 있다.

문서 위치는:

``` text
section_path 존재
      ↓
" > "로 연결

없음
      ↓
title

둘 다 없음
      ↓
"문서 위치 미상"
```

순서로 만든다.

------------------------------------------------------------------------

# 4. Prompt 생성

## 4.1 `prompt_builder.py`

`build_prompt()`가 LLM에 전달할 Prompt를 구성한다.

입력:

``` text
query
announcement_directory
document_format
sources
```

출력:

``` text
PromptPayload
```

## 4.2 System Prompt

현재 System Prompt의 주요 규칙은 다음과 같다.

-   선택한 LH 공고 근거만 사용
-   다른 공고·인터넷·상식·추측으로 보완 금지
-   근거에서 확인되지 않으면 확인할 수 없다고 답변
-   금액·날짜·면적·세대수·자격 기준 등을 임의 변경하지 않음
-   표의 행/열 관계 유지
-   충돌하는 정보를 임의 선택하지 않음
-   법률·정책의 최종 판단을 하지 않음
-   한국어로 답변
-   사용자 답변에 근거 번호를 표시하지 않음
-   Chunk ID 및 검색 점수 등의 내부정보를 노출하지 않음

## 4.3 User Prompt

User Prompt에는 다음 정보가 포함된다.

``` text
[선택한 LH 공고]
announcement_directory

[문서 형식]
document_format

[사용자 질문]
query

[LH 공고문 근거]
SourceContext 내용
```

그리고 제공된 LH 공고문 근거만 사용하고 추측하지 않도록 하는 지시가
추가된다.

## 4.4 OpenAI Chat 형식 변환

`PromptPayload.to_messages()`는 Prompt를 다음 형식으로 변환한다.

``` json
[
  {
    "role": "system",
    "content": "..."
  },
  {
    "role": "user",
    "content": "..."
  }
]
```

이 `messages`가 llama.cpp 요청에 그대로 사용된다.

------------------------------------------------------------------------

# 5. llama.cpp 설정

## 5.1 `config.py`

현재 주요 설정은 다음과 같다.

  설정                 기본값
  -------------------- -------------------------
  Base URL             `http://127.0.0.1:8080`
  Endpoint             `/v1/chat/completions`
  Temperature          `0.0`
  Top P                `1.0`
  Max Tokens           `1024`
  Timeout              `180초`
  Context Top-K        `5`
  Context 문자 제한    `6000`
  Source Marker 검사   `True`

주요 환경변수는:

``` text
LLAMA_BASE_URL
LLAMA_MODEL
LLAMA_TEMPERATURE
LLAMA_TOP_P
LLAMA_MAX_TOKENS
LLAMA_TIMEOUT_SECONDS
LLAMA_CONTEXT_TOP_K
LLAMA_MAX_CONTEXT_CHARS
```

이다.

`LLAMA_MODEL`이 비어 있으면 Config Validation에서 오류가 발생한다.

------------------------------------------------------------------------

# 6. Generation ↔ llama.cpp 연결

이 부분이 현재 Generation 구조에서 중요한 외부 연결이다.

## 6.1 연결 구조

현재 연결은:

``` text
generator.py
      ↓ Python import
llm_client.py
      ↓
call_llama_cpp_chat()
      ↓
HTTP POST
      ↓
llama.cpp llama-server
```

이다.

기본 설정을 기준으로 실제 요청 대상은:

``` text
http://127.0.0.1:8080
        +
/v1/chat/completions
        ↓
http://127.0.0.1:8080/v1/chat/completions
```

이다.

즉 llama.cpp의 Python 모듈이나 함수를 직접 import하는 것이 아니다.

## 6.2 `/v1/chat/completions`의 의미

여기서 `/v1/chat/completions`는 FastAPI에서 직접 만든 프로젝트 라우터가
아니다.

현재 코드에서 확인되는 구조는:

``` text
Generation
    │
    │ HTTP POST
    ▼
127.0.0.1:8080
    │
    ▼
llama.cpp llama-server
    │
    └─ /v1/chat/completions
```

이다.

Generation은 **llama.cpp 서버가 제공하는 OpenAI 호환 Chat API
Endpoint**로 요청을 보낸다.

따라서 현재 구조를 구분하면:

``` text
Generation 내부
→ Python 함수 호출

Generation → llama.cpp
→ HTTP API 호출
```

이다.

## 6.3 llama.cpp 요청 Payload

`llm_client.py`가 전송하는 주요 데이터는:

``` text
model
messages
temperature
top_p
max_tokens
stream
```

이다.

개념적으로:

``` json
{
  "model": "...",
  "messages": [
    {
      "role": "system",
      "content": "..."
    },
    {
      "role": "user",
      "content": "..."
    }
  ],
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 1024,
  "stream": false
}
```

형태이다.

Python 표준 라이브러리 `urllib.request`를 사용하여 JSON을 HTTP POST로
전송한다.

## 6.4 llama.cpp 쪽 모델과 `LLAMA_MODEL`

현재 Generation 요청의:

``` text
LLAMA_MODEL
```

값은 HTTP Payload의:

``` text
"model": "..."
```

에 들어간다.

따라서 코드에서 확인되는 관계는:

``` text
Generation 환경변수
LLAMA_MODEL
      ↓
HTTP Request
"model"
      ↓
llama.cpp Server
```

이다.

실제 개발 과정에서도 llama-server에 설정된 모델 이름과 이 값이 맞지
않았을 때:

``` text
400 model not found
```

문제가 발생한 적이 있다.

## 6.5 현재 문서에서 확인 가능한 llama.cpp 구성 범위

현재 Generation 코드에서 확실하게 확인되는 것은:

``` text
llama.cpp는 별도 HTTP Server로 실행됨

Port 기본값 = 8080

Generation 기본 접속 주소
= http://127.0.0.1:8080

사용 Endpoint
= /v1/chat/completions

HTTP Method
= POST

OpenAI 호환 Chat 형식 사용

모델 이름
= LLAMA_MODEL로 전달
```

까지이다.

반면 **llama-server 실행 명령 전체, GGUF 파일 경로, `--ctx-size`, GPU
Layer 등의 서버 실행 옵션은 지금 제공한 Generation 코드 자체에서
확인되는 내용이 아니므로 이 코드리뷰에서 임의로 추가하지 않는다.**

------------------------------------------------------------------------

# 7. `llm_client.py`

## 7.1 역할

`call_llama_cpp_chat()`가 Prompt를 llama.cpp에 전달하고 응답을 읽는다.

``` text
PromptPayload
      ↓
to_messages()
      ↓
JSON Payload
      ↓
urllib.request
      ↓
HTTP POST
      ↓
llama.cpp
      ↓
JSON Response
```

## 7.2 응답 처리

llama.cpp 응답 JSON에서:

``` text
choices[0]
   ↓
message
   ↓
content
```

를 추출하여 LLM 답변 문자열로 사용한다.

다음 상황은 오류로 처리한다.

``` text
choices 없음
choices[0] 형식 오류
message 없음
content 없음/빈 값
finish_reason = length
```

## 7.3 HTTP 오류 처리

다음 오류들을 처리한다.

``` text
HTTPError
URLError
TimeoutError
OSError
JSONDecodeError
```

llama.cpp 서버에 연결할 수 없는 경우 `LLMClientError`를 발생시킨다.

------------------------------------------------------------------------

# 8. 답변 생성 및 검증

## 8.1 `generator.py`

전체 Generation을 조율한다.

``` text
retrieval_results
      ↓
build_source_contexts()
      ↓
build_prompt()
      ↓
call_llama_cpp_chat()
      ↓
remove_source_markers()
      ↓
validate_korean_answer()
      ↓
GeneratedAnswer
```

## 8.2 Source Marker 제거

LLM 응답에:

``` text
[근거 1]
[근거 2]
[출처 1]
```

등이 포함되면 `remove_source_markers()`가 사용자 답변에서 제거한다.

단, 실제 근거 객체 자체를 제거하는 것은 아니며
`GeneratedAnswer.sources`에는 유지된다.

## 8.3 답변 검증

`validate_korean_answer()`에서는 주요하게 다음을 확인한다.

``` text
빈 답변 금지

중국어/일본어 문자 금지

Prompt 내부정보 노출 금지

Chunk ID 노출 금지

검색 점수명 노출 금지

role 관련 내부 문자열 노출 금지
```

예를 들어:

``` text
[LH 공고문 근거]
[사용자 질문]
[선택한 LH 공고]
청크 ID:
문서 위치:
reranker_score
fusion_score
vector_score
keyword_score
system_prompt
user_prompt
```

등의 내부 문자열이 사용자 답변에 포함되는지 검사한다.

## 8.4 1회 재생성

첫 번째 답변이 검증에 실패하면 강화된 지시를 추가하여 llama.cpp를 한 번
더 호출한다.

``` text
1차 llama.cpp 호출
       ↓
Answer
       ↓
Validation
   ┌───┴────┐
 성공      실패
   │         ↓
   │    Retry Prompt
   │         ↓
   │    llama.cpp 재호출
   │         ↓
   │      재검증
   │
   └─────────┘
```

두 번째 검증도 실패하면 코드에 정의된 고정 메시지를 반환한다.

------------------------------------------------------------------------

# 9. Generation 출력

## 9.1 `GeneratedAnswer`

Generation의 최종 결과는 파일이 아니라 Python 객체다.

``` text
GeneratedAnswer
├─ answer
├─ query
├─ announcement_directory
├─ document_format
├─ sources
├─ prompt
└─ raw_response
```

즉 다음 정보가 함께 유지된다.

``` text
최종 답변
사용자 질문
사용한 Source Context
실제 Prompt
llama.cpp 원본 Response
```

Generation 코드 자체에서는 `.json`, `.txt` 등의 답변 파일을 생성하지
않는다.

------------------------------------------------------------------------

# 10. 다른 코드와의 연결

## 10.1 주요 연결 관계

  ----------------------------------------------------------------------------------
  호출하는 쪽           호출받는 쪽              연결 방식         역할
  --------------------- ------------------------ ----------------- -----------------
  `generator.py`        `context_builder.py`     Python import     Retrieval →
                                                                   SourceContext

  `generator.py`        `prompt_builder.py`      Python import     Prompt 생성

  `prompt_builder.py`   `context_builder.py`     Python import     Context Block
                                                                   생성

  `generator.py`        `llm_client.py`          Python import     LLM 호출

  `llm_client.py`       llama.cpp Server         **HTTP POST**     답변 생성

  `llm_client.py`       `/v1/chat/completions`   HTTP API          OpenAI 호환 Chat
                                                                   요청

  `generator.py`        Backend ErrorLog         Python import     Generation 오류
                                                                   기록
  ----------------------------------------------------------------------------------

## 10.2 Backend ErrorLog

`generator.py`에는:

``` python
from backend.app.services.error_log_service import record_error
```

직접 import가 존재한다.

따라서 현재 관계는:

``` text
Generation
     ↓ Python import
Backend ErrorLog Service
```

이다.

Generation 오류 발생 시:

``` text
error_type = llm
stage = generation
message
error_code
stack_trace
```

등을 전달한다.

------------------------------------------------------------------------

# 11. Generation 전체 실행 구조

``` text
[Retrieval]

SearchResult[]
      │
      │ Python 객체
      ▼
────────────────────────────────
           GENERATION
────────────────────────────────

context_builder.py
      ↓
SourceContext[]
      ↓
prompt_builder.py
      ↓
PromptPayload
      ↓
generator.py
      ↓
llm_client.py

────────────────────────────────
        HTTP CONNECTION
────────────────────────────────

      HTTP POST
          ↓
http://127.0.0.1:8080
          ↓
/v1/chat/completions
          ↓
llama.cpp llama-server
          ↓
서버에 로드된 LLM
          ↓
JSON Response

────────────────────────────────
          GENERATION
────────────────────────────────

choices[0].message.content
          ↓
Source Marker 제거
          ↓
한국어/내부정보 검증
          ↓
필요 시 llama.cpp 1회 재호출
          ↓
GeneratedAnswer
```

따라서 Generation의 현재 경계를 한 문장으로 정리하면:

> **Retrieval 결과를 근거 Context와 Prompt로 구성한 뒤, llama.cpp의
> OpenAI 호환 `/v1/chat/completions` Endpoint를 HTTP POST로 호출하고,
> 반환된 답변을 후처리·검증하여 `GeneratedAnswer` Python 객체로
> 반환한다.**

------------------------------------------------------------------------

# 12. llama.cpp 연결 구조 핵심 정리

Generation 코드리뷰에서 이 부분은 따로 남겨두는 게 좋다.

``` text
                 [RAG Generation]
                         │
                         │ HTTP POST
                         ▼
              http://127.0.0.1:8080
                         │
                         ▼
              /v1/chat/completions
                         │
                         ▼
               llama.cpp llama-server
                         │
                         ▼
                로드되어 있는 LLM
                         │
                         ▼
                  JSON Response
                         │
                         ▼
                 [RAG Generation]
```

여기서 중요한 구분은 다음과 같다.

``` text
RAG 내부 모듈 연결
→ Python import / 함수 호출

Generation → llama.cpp
→ HTTP API

/v1/chat/completions
→ llama.cpp 서버가 제공하는 Endpoint

LLAMA_MODEL
→ HTTP 요청의 model 값

LLAMA_BASE_URL
→ llama.cpp 서버 주소
```

즉 **llama.cpp는 Generation 코드 안에 라이브러리처럼 들어가 있는 것이
아니라 별도로 실행 중인 `llama-server`이고, Generation이 HTTP Client가
되어 그 서버를 호출하는 구조**다.

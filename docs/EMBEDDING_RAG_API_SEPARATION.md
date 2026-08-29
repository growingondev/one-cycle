# Embedding API & RAG API 분리·연동 작업 문서

> **문서 목적**\
> 이 문서는 `one-cycle_api` 프로젝트에서 수행한 **Embedding API 서비스
> 분리**와 **RAG API 분리 및 Embedding API 연동** 작업을 인수인계하기
> 위한 문서입니다.\
> 이후 다른 팀원이 Document Worker/Pipeline 연동, Docker 서비스 통합,
> Backend 연동, 코드 정리를 진행할 때 현재 구현 상태와 서비스 경계를
> 바로 파악할 수 있도록 작성했습니다.

------------------------------------------------------------------------

## 1. 작업 범위

이번 작업에서 완료한 범위는 다음 두 가지입니다.

### 1.1 Embedding API 분리 및 구현

기존에는 필요한 코드에서 BGE-M3 모델을 직접 import/load하여 임베딩을
생성하는 구조였습니다.

이를 **공용 Embedding Service**로 분리하여, 다른 서비스가 직접 BGE-M3를
로드하지 않고 HTTP API를 통해 임베딩을 요청할 수 있도록 구현했습니다.

### 1.2 RAG API 분리 및 Retrieval의 Embedding API 연동

RAG를 별도 HTTP API 서비스로 구성했습니다.

또한 RAG Retrieval 과정에서 기존처럼 BGE-M3를 직접 호출하지 않고, 앞에서
만든 **Embedding Service의 `/v1/embeddings` API를 HTTP로 호출**하도록
변경했습니다.

Generation은 기존부터 `llama.cpp server`를 HTTP로 호출하는 구조였으므로
API 분리를 위해 별도의 구조 변경을 하지 않았습니다.

------------------------------------------------------------------------

## 2. 현재 전체 구조

``` text
Backend
   │
   │ HTTP
   ▼
┌──────────────────────────┐
│       RAG Service        │
│          :18002          │
│ POST /v1/rag/answer      │
└────────────┬─────────────┘
             │
             ├─────────────── PostgreSQL
             │                 - Vector Search
             │                 - BM25
             │                 - RRF
             │
             │ HTTP
             ▼
     ┌─────────────────────┐
     │ Embedding Service   │
     │       :18001        │
     │ POST /v1/embeddings │
     │ BAAI/bge-m3         │
     └─────────────────────┘
             │
             │
             └── Query Embedding

RAG Service
   │
   │ HTTP
   ▼
llama.cpp server :8080
   │
   ▼
Gemma
   │
   ▼
최종 답변 생성
```

향후 Document Worker가 완료되면 다음 연결이 추가되어야 합니다.

``` text
Document Worker
      │
      │ HTTP
      ▼
Embedding Service :18001
      │
      ▼
Chunk Embedding
```

즉, 최종 목표는 **RAG와 Document Worker 모두 동일한 Embedding Service를
사용**하는 구조입니다.

------------------------------------------------------------------------

## 3. Embedding API 작업

### 3.1 작업 목적

기존 구조에서는 RAG와 문서 처리 과정 등에서 BGE-M3 모델을 직접
import/load할 수 있었습니다.

서비스 분리 후의 원칙은 다음과 같습니다.

``` text
잘못된 구조

RAG -----------------> BGE-M3 직접 load
Document Pipeline ---> BGE-M3 직접 load


변경 구조

RAG --------------┐
                   │ HTTP
                   ▼
             Embedding Service
                   │
                   ▼
                 BGE-M3
                   ▲
                   │ HTTP
Document Worker ---┘
```

**BGE-M3 모델 실행 책임은 Embedding Service에만 둡니다.**

외부 서비스에서 `load_bge_m3_model()`, `model.encode()` 등의 방식으로
직접 모델을 실행하지 않는 것이 서비스 분리의 핵심입니다.

------------------------------------------------------------------------

## 4. Embedding Service 파일 구성

현재 주요 파일은 다음과 같습니다.

``` text
services/
└── embedding/
    ├── __init__.py
    ├── main.py
    ├── schemas.py
    ├── service.py
    └── client.py
```

### `services/embedding/main.py`

Embedding FastAPI 서버 진입점입니다.

주요 역할:

-   FastAPI 애플리케이션 생성
-   서비스 시작 시 Embedding 모델 준비
-   `/health` 제공
-   `POST /v1/embeddings` 제공
-   요청 검증 오류 및 서비스 오류를 HTTP 응답으로 변환

AWS 테스트 포트:

``` text
127.0.0.1:18001
```

------------------------------------------------------------------------

### `services/embedding/schemas.py`

Embedding API의 Request/Response 스키마를 정의합니다.

주요 검증:

-   `items` 최소 1개
-   요청 내 `id` 중복 금지
-   `text`는 공백만 있는 문자열 금지
-   성공 응답에서 각 item에 ID와 embedding 반환

------------------------------------------------------------------------

### `services/embedding/service.py`

Embedding Service 내부의 실제 모델 실행 계층입니다.

현재 이 파일은 기존 `pipeline.embedding`의 핵심 구현을 재사용하고
있습니다.

즉 현재 구조는:

``` text
Embedding API
   ↓
services/embedding/service.py
   ↓
pipeline.embedding 내부 모델 실행 코드
   ↓
BGE-M3
```

이 부분은 **외부 서비스가 BGE-M3를 직접 호출하는 것과는 다릅니다.**

Embedding Service 자신은 실제 모델을 실행해야 하므로 모델 실행 코드가
필요합니다.

다만 향후 물리적인 서비스 경계를 더 명확히 할 경우,
`pipeline.embedding`에 있는 순수 모델 실행 코드를 `services/embedding`
내부로 이동하는 리팩터링을 검토할 수 있습니다.

------------------------------------------------------------------------

### `services/embedding/client.py`

**Embedding 서버 코드가 아니라 Embedding Service를 호출하기 위한 HTTP
Client입니다.**

현재 RAG가 이 Client를 사용합니다.

역할:

``` text
RAG
 ↓
EmbeddingClient
 ↓ HTTP POST
/v1/embeddings
 ↓
Embedding Service
```

향후 Document Worker에서도 동일한 API 계약을 사용해야 합니다.

Client는 응답에서 다음 내용을 검증합니다.

-   HTTP 성공 여부
-   model
-   dimension
-   normalized
-   요청 ID와 응답 ID 일치
-   vector shape
-   finite vector 여부

------------------------------------------------------------------------

## 5. Embedding API 계약

### Endpoint

``` http
POST /v1/embeddings
```

### Request 예시

``` json
{
  "items": [
    {
      "id": "chunk-001",
      "text": "임베딩할 문장"
    }
  ]
}
```

RAG Query Embedding은 다음처럼 단일 item으로 요청합니다.

``` json
{
  "items": [
    {
      "id": "query",
      "text": "신청 기간은 언제인가요?"
    }
  ]
}
```

### Response 예시

``` json
{
  "model": "BAAI/bge-m3",
  "dimension": 1024,
  "normalized": true,
  "items": [
    {
      "id": "chunk-001",
      "embedding": []
    }
  ]
}
```

### 현재 모델 규격

``` text
Model      : BAAI/bge-m3
Dimension  : 1024
Normalized : true
```

### ID 처리 규칙

응답 배열 순서에 의존하지 않습니다.

반드시:

``` text
request item.id ↔ response item.id
```

로 결과를 매칭해야 합니다.

------------------------------------------------------------------------

## 6. Embedding API AWS 검증 결과

AWS 환경에서 실제 BGE-M3를 GPU에 로드하여 테스트했습니다.

확인된 항목:

``` text
Embedding Service 실행       성공
BGE-M3 모델 로드             성공
NVIDIA L4 GPU 사용           성공
GET /health                  성공
단일 Query Embedding         성공
Batch Chunk Embedding        성공
1024 dimension               확인
normalized=true              확인
중복 ID Validation           성공
공백 Text Validation         성공
```

Embedding API 자체의 기능 검증은 완료된 상태입니다.

------------------------------------------------------------------------

# 7. RAG API 작업

## 7.1 작업 목적

기존 RAG는 Python 내부 함수 호출 형태로 사용될 수 있었고, Retrieval
과정에서 BGE-M3 모델을 직접 사용하는 구조가 존재했습니다.

변경 목표:

``` text
Backend
   ↓ HTTP
RAG Service
   ↓
Retrieval
   ↓ HTTP
Embedding Service
```

즉 RAG 자체도 독립적인 API 서비스로 만들고, RAG 내부 Query Embedding도
공용 Embedding Service를 사용하도록 변경했습니다.

------------------------------------------------------------------------

## 8. RAG Service 파일 구성

``` text
services/
└── rag/
    ├── __init__.py
    ├── main.py
    ├── schemas.py
    └── service.py
```

기존 RAG 내부 로직은 별도 폴더에 유지합니다.

``` text
rag/
├── db_pipeline.py
├── retrieval/
└── generation/
```

역할 구분은 다음과 같습니다.

``` text
services/rag/
    = HTTP API / 서비스 진입 계층

rag/
    = Retrieval / Generation 등 실제 RAG 내부 로직
```

------------------------------------------------------------------------

### `services/rag/main.py`

RAG FastAPI 서버 진입점입니다.

현재 제공 API:

``` http
GET /health
POST /v1/rag/answer
```

AWS 테스트 포트:

``` text
127.0.0.1:18002
```

------------------------------------------------------------------------

### `services/rag/schemas.py`

RAG API Request/Response를 정의합니다.

Request:

``` json
{
  "announcement_id": 52,
  "question": "신청 기간은 언제인가요?"
}
```

주요 검증:

-   `announcement_id >= 1`
-   빈 question 금지

------------------------------------------------------------------------

### `services/rag/service.py`

HTTP API와 기존 RAG 내부 로직 사이의 서비스 계층입니다.

대략적인 호출 흐름:

``` text
POST /v1/rag/answer
        ↓
services/rag/service.py
        ↓
DBRAGPipeline
        ↓
Retrieval + Generation
```

RAG 결과를 다음 비즈니스 상태로 변환합니다.

``` text
grounded
no_evidence
unsupported
```

`no_evidence`는 서버 장애가 아니라 **검색 가능한 근거가 없다는 정상
비즈니스 응답**입니다.

------------------------------------------------------------------------

## 9. Retrieval의 Embedding API 전환

이번 RAG 작업에서 가장 중요한 변경 중 하나입니다.

### 기존

``` text
Question
   ↓
RAG Retrieval
   ↓
BGE-M3 직접 호출
   ↓
Query Vector
```

### 변경 후

``` text
Question
   ↓
RAG Retrieval
   ↓
services/embedding/client.py
   ↓ HTTP
POST /v1/embeddings
   ↓
Embedding Service
   ↓
BGE-M3
   ↓
Query Vector 반환
```

현재 `rag/db_pipeline.py`는 `EmbeddingClient`를 통해 Query Embedding을
요청하도록 변경되어 있습니다.

따라서 **현재 실제 RAG 실행 경로에서는 Query Embedding을 위해 BGE-M3를
직접 로드하지 않습니다.**

------------------------------------------------------------------------

## 10. 기존 `query_embedding.py`에 대한 주의

현재 다음과 같은 기존 코드가 저장소에 남아 있을 수 있습니다.

``` text
rag/retrieval/query_embedding.py
```

이 파일은 기존 직접 임베딩 방식의 코드입니다.

현재 production RAG 실행 경로는 `EmbeddingClient`를 사용하도록
변경했으므로 이 파일은 추후 정리 대상입니다.

**다만 다른 평가 코드나 레거시 코드에서 참조할 가능성을 확인하기 전에는
바로 삭제하지 않습니다.**

------------------------------------------------------------------------

# 11. RAG Retrieval 흐름

현재 RAG Retrieval은 다음 순서로 동작합니다.

``` text
사용자 질문
   ↓
Embedding API
   ↓
Query Vector
   ↓
Vector Search ──┐
                │
BM25 Search ────┤
                ↓
               RRF
                ↓
          Hybrid Search 결과
                ↓
             Evidence
```

검색은 반드시 전달받은:

``` text
announcement_id
```

범위 안에서 수행합니다.

------------------------------------------------------------------------

# 12. Generation 부분

Generation은 이번 API 분리에서 구조를 변경하지 않았습니다.

이유는 기존부터 이미:

``` text
RAG
 ↓ HTTP
llama.cpp server
 ↓
Gemma
```

형태였기 때문입니다.

즉 이번 작업에서:

``` text
Retrieval → Embedding
```

은 직접 Python 호출에서 HTTP API로 변경했지만,

``` text
Generation → llama.cpp
```

는 원래 HTTP 통신이었기 때문에 그대로 유지했습니다.

------------------------------------------------------------------------

# 13. AWS RAG 통합 테스트 결과

최종적으로 다음 전체 흐름을 실제 AWS에서 확인했습니다.

``` text
POST /v1/rag/answer
        ↓
RAG Service :18002
        ↓
EmbeddingClient
        ↓ HTTP
Embedding Service :18001
        ↓
BGE-M3 Query Embedding
        ↓
PostgreSQL Retrieval
(Vector + BM25 + RRF)
        ↓
Context / Prompt
        ↓ HTTP
llama.cpp :8080
        ↓
Gemma
        ↓
Answer
        ↓
RAG API Response
```

**최종 답변까지 정상 반환되는 것을 확인했습니다.**

따라서 현재:

``` text
Embedding API                    검증 완료
RAG API                          검증 완료
RAG → Embedding HTTP 연결        검증 완료
Retrieval                        실행 확인
RAG → llama.cpp HTTP 연결        실행 확인
최종 Grounded Answer             확인
```

상태입니다.

------------------------------------------------------------------------

# 14. 통합 테스트 중 확인한 이슈 1 --- `no_evidence`

초기 테스트에서 `announcement_id=1`을 사용했을 때:

``` json
{
  "result": "no_evidence",
  "grounded": false,
  "evidence": []
}
```

가 반환되었습니다.

처음에는 Embedding/Retrieval 오류 가능성을 확인했으나 DB를 점검한 결과
announcement 1에는 정상적으로:

``` text
chunks     : 233
embeddings : 233
model      : BAAI/bge-m3
dimension  : 1024
normalized : true
```

가 존재했습니다.

원인은 Collection 상태였습니다.

``` text
system_state.active_collection_run_id = 2

announcement_id = 1
announcement.collection_run_id = 1
```

현재 Vector Search와 BM25 SQL은 모두 **active collection에 속한
announcement만 검색**합니다.

따라서 announcement 1은 데이터가 없는 것이 아니라 **현재 active
collection이 아니기 때문에 검색 대상에서 제외된 것**입니다.

이후 active collection에 속한 announcement를 이용해 테스트를
계속했습니다.

### 후속 통합 작업 시 주의

Backend에서 사용자에게 보여주는 공고와 RAG가 검색하는 active
collection의 기준이 일치해야 합니다.

또한 collection publish 과정에서 모든 처리 완료 전에
`active_collection_run_id`가 변경되지 않는지 팀 단위로 확인할 필요가
있습니다.

------------------------------------------------------------------------

# 15. 통합 테스트 중 확인한 이슈 2 --- Gemma Reasoning

active announcement로 RAG 전체 테스트를 진행했을 때 Generation 단계에서
다음 오류가 발생했습니다.

``` text
finish_reason = "length"
content = ""
reasoning_content = 매우 긴 추론
completion_tokens = 1024
```

즉 API 연결 문제가 아니라 Gemma가 출력 토큰을 `reasoning_content`에 모두
사용하여 실제 답변 `content`를 생성하기 전에 토큰 제한에 도달한
문제였습니다.

현재 llama.cpp 버전에서 다음 옵션을 지원하는 것을 확인했습니다.

``` text
--reasoning [on|off|auto]
--reasoning-budget N
```

테스트에서는 llama-server 실행 시:

``` text
--reasoning off
```

를 적용했고 이후 RAG 최종 답변이 정상 반환되었습니다.

### 현재 테스트한 llama-server 주요 설정

``` text
model     : gemma-4-12B-it-Q4_0.gguf
alias     : gemma
host      : 127.0.0.1
port      : 8080
ctx-size  : 8192
GPU layer : 999
threads   : 4
reasoning : off
```

이 설정은 Docker/운영 실행 명령 구성 시 반드시 다시 반영 여부를 확인해야
합니다.

------------------------------------------------------------------------

# 16. 현재 완료 상태

  작업                                 상태
  ------------------------------------ ---------------------
  Embedding Service API 생성           완료
  `/v1/embeddings` 구현                완료
  Embedding 단일 요청 테스트           완료
  Embedding Batch 테스트               완료
  Embedding Validation 테스트          완료
  RAG Service API 생성                 완료
  `/v1/rag/answer` 구현                완료
  RAG Query Embedding 직접 호출 제거   완료
  RAG → Embedding HTTP 연결            완료
  RAG Retrieval 실행                   완료
  RAG → llama.cpp 연결                 기존 HTTP 구조 유지
  AWS 전체 RAG E2E 테스트              완료
  Document Pipeline → Embedding API    **대기**
  레거시 Embedding 코드 정리           **대기**
  Docker 서비스 단위 통합              **대기**

------------------------------------------------------------------------

# 17. 현재 하지 않은 작업

## Document Pipeline / Worker의 Chunk Embedding API 전환

이 부분은 아직 변경하지 않았습니다.

현재 기존 문서 처리 흐름에는 다음과 같은 직접 임베딩 실행 코드가 남아
있습니다.

``` text
pipeline/embedding/run_embeddings.py
```

검색 결과 이 파일에서는 현재:

``` text
load_bge_m3_model()
generate_embeddings()
```

등을 직접 사용합니다.

또한:

``` text
pipeline/document_processor.py
```

가 기존 `run_embeddings.py` 실행 경로를 가지고 있습니다.

하지만 Document Pipeline/Worker API 작업은 다른 팀원의 작업 결과와 맞춰
연결해야 하므로 **이번 작업에서는 해당 코드를 임의로 수정하지
않았습니다.**

------------------------------------------------------------------------

# 18. Document Worker 담당자가 이어서 해야 할 작업

Document Worker/API 작업이 완료되면 Chunk Embedding 부분을 다음 구조로
연결해야 합니다.

### 기존

``` text
Document Worker / Pipeline
        ↓
run_embeddings.py
        ↓
BGE-M3 직접 load
        ↓
Chunk Embedding
```

### 목표

``` text
Document Worker
        ↓
Chunk/Text 준비
        ↓ HTTP
POST /v1/embeddings
        ↓
Embedding Service
        ↓
BGE-M3
        ↓
Embedding 결과
        ↓
Worker에서 저장/후속 처리
```

중요한 책임 분리는 다음과 같습니다.

### Document Worker 책임

-   HWP/HWPX Parsing
-   Normalizing
-   Structure 생성
-   Chunking
-   임베딩할 text 결정
-   Chunk ID 결정
-   Embedding API 요청
-   반환 vector와 chunk ID 매칭
-   DB/Artifact 저장 및 후속 처리

### Embedding Service 책임

-   BGE-M3 모델 로드
-   Encode/Inference
-   Dense Vector 생성
-   L2 Normalization
-   Vector 결과 검증
-   API Response 반환

즉 **문서 파이프라인 전체를 Embedding Service로 옮기면 안 됩니다.**

Embedding Service는 **텍스트를 받아 벡터를 반환하는 공용 모델
서비스**입니다.

------------------------------------------------------------------------

# 19. 향후 코드 정리 대상

통합 작업 후 아래 항목을 점검해야 합니다.

### 19.1 기존 Query Embedding 코드

``` text
rag/retrieval/query_embedding.py
```

현재 실제 RAG 경로에서 사용하지 않는다면 참조 여부 확인 후 제거합니다.

------------------------------------------------------------------------

### 19.2 `pipeline/embedding/run_embeddings.py`

Document Worker가 Embedding API를 사용하도록 변경된 후 기존 CLI가
필요한지 판단합니다.

테스트/수동 실행 용도로 유지할 수도 있으므로 바로 삭제하지 않습니다.

------------------------------------------------------------------------

### 19.3 RAG의 Backend 직접 import

현재 일부 RAG 내부 코드에는 다음과 같은 Backend 의존성이 남아 있습니다.

``` text
backend.app.db.session.SessionLocal
backend.app.services.error_log_service
```

RAG를 완전히 독립된 Docker 서비스로 분리할 경우 이 의존성을 검토해야
합니다.

특히 RAG가 DB에 직접 접근하는 현재 설계를 유지한다면 RAG 자체 DB
session/config 계층으로 분리하는 방안을 검토해야 합니다.

------------------------------------------------------------------------

### 19.4 Embedding Client 오류 계약

서비스 간 공통 오류 계약:

``` json
{
  "error": {
    "code": "SERVICE_ERROR_CODE",
    "message": "Error message."
  }
}
```

최종 통합 시 Embedding Client가 downstream HTTP status / error code /
message를 계약에 맞게 보존하는지 재검토합니다.

------------------------------------------------------------------------

### 19.5 requirements

다음과 같은 직접 의존성이 최종 requirements에 포함되어 있는지
확인합니다.

``` text
fastapi
uvicorn
httpx
```

Embedding Service의 ML/GPU dependency도 서비스별 Docker 구성 시 다시
분리할 수 있습니다.

------------------------------------------------------------------------

# 20. 환경변수 / 서비스 주소

현재 Host-level AWS 통합 테스트에서는 다음 형태를 사용했습니다.

``` text
Embedding Service
http://127.0.0.1:18001

RAG Service
http://127.0.0.1:18002

llama.cpp
http://127.0.0.1:8080
```

RAG에서 Embedding Service 주소는:

``` text
EMBEDDING_SERVICE_URL
```

을 사용합니다.

### Docker 전환 시 중요

각 서비스가 별도 Container가 되면:

``` text
127.0.0.1
```

은 자기 자신의 Container를 의미합니다.

따라서 Docker Compose에서는 서비스 이름 기반 주소로 변경해야 합니다.

예:

``` text
http://embedding:18001
```

실제 이름/포트는 최종 `docker-compose.yml`에 맞춰 결정합니다.

------------------------------------------------------------------------

# 21. 서비스 실행 및 확인 예시

## Embedding Service

``` bash
python -m uvicorn services.embedding.main:app \
  --host 127.0.0.1 \
  --port 18001
```

Health:

``` bash
curl -s http://127.0.0.1:18001/health
```

------------------------------------------------------------------------

## RAG Service

``` bash
python -m uvicorn services.rag.main:app \
  --host 127.0.0.1 \
  --port 18002
```

Health:

``` bash
curl -s http://127.0.0.1:18002/health
```

RAG 테스트:

``` bash
curl -s -X POST http://127.0.0.1:18002/v1/rag/answer \
  -H "Content-Type: application/json" \
  -d '{"announcement_id":52,"question":"신청 기간은 언제인가요?"}'
```

테스트할 `announcement_id`는 **현재 active collection에 속한 공고**를
사용해야 합니다.

------------------------------------------------------------------------

# 22. 다음 통합 작업자가 먼저 확인할 것

이 작업을 이어받는 경우 아래 순서로 확인하는 것을 권장합니다.

1.  `services/embedding/` 구조와 `/v1/embeddings` 계약 확인
2.  `services/embedding/client.py`가 서버가 아니라 **호출용 HTTP
    Client**임을 확인
3.  `rag/db_pipeline.py`에서 Query Embedding이 `EmbeddingClient`를
    사용하는지 확인
4.  Embedding Service 실행 후 `/health` 확인
5.  RAG Service 실행 후 `/health` 확인
6.  active collection에 속한 announcement로 `/v1/rag/answer` 테스트
7.  llama.cpp 실행 시 Gemma reasoning 설정 확인
8.  Document Worker 작업이 완료되면 Chunk Embedding을 `/v1/embeddings`로
    연결
9.  모든 연결 완료 후 레거시 직접 Embedding 호출 코드 정리
10. Docker 환경에서는 localhost 대신 서비스 hostname으로 변경

------------------------------------------------------------------------

# 23. 최종 서비스 경계

최종적으로 지켜야 할 구조는 다음과 같습니다.

``` text
Backend
   │
   ├── HTTP → Document Worker
   │
   └── HTTP → RAG Service
                   │
                   ├── DB → PostgreSQL
                   │
                   ├── HTTP → Embedding Service
                   │              │
                   │              └── BGE-M3
                   │
                   └── HTTP → llama.cpp
                                  │
                                  └── Gemma

Document Worker
   │
   └── HTTP → Embedding Service
```

### 핵심 원칙

``` text
BGE-M3를 사용하는 외부 서비스
        ↓
직접 import/load 하지 않음
        ↓
Embedding API를 호출
```

Embedding Service만 실제 Embedding 모델 실행 책임을 가집니다.

------------------------------------------------------------------------

# 24. 인수인계 요약

현재 완료된 핵심은 다음과 같습니다.

**Embedding** - 공용 Embedding API 서비스 구현 완료 - BGE-M3 실제 AWS
GPU 실행 검증 완료 - Query/Batch/Validation 테스트 완료

**RAG** - RAG API 서비스 구현 완료 - Retrieval의 직접 BGE-M3 호출을
Embedding HTTP API 호출로 변경 완료 - 기존 Vector + BM25 + RRF 검색 흐름
유지 - Generation은 기존 llama.cpp HTTP 연결 유지 - AWS에서 최종
답변까지 E2E 검증 완료

**남은 핵심** - 다른 팀원의 Document Worker/API 작업 완료 후 Chunk
Embedding을 동일한 Embedding API에 연결 - 이후 레거시 직접 임베딩 코드
및 서비스 간 잔여 직접 의존성 정리 - Docker 서비스 단위 최종 통합 및
재검증

이 문서를 기준으로 이후 작업자는 **Embedding 모델을 새로 직접 로드하는
코드를 추가하지 말고, `/v1/embeddings` 계약을 사용하여 서비스에
연결**해야 합니다.

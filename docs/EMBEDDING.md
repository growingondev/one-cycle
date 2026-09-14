# Embedding

> 기준 브랜치: `main`  
> 기준 구현: `document_worker/service.py`, `services/embedding/`, `pipeline/embedding/`  
> 이 문서는 DDOK BOT 서비스에서 Chunk가 실제로 어떻게 Dense Vector로 변환되는지 설명한다.

---

## 1. 개요

Embedding은 Chunking 결과의 `embedding_text`를 벡터로 변환하여 이후 Vector Search에서 사용할 수 있도록 만드는 단계다.

현재 DDOK BOT은 다음 Embedding 모델을 사용한다.

```text
BAAI/bge-m3
```

현재 서비스에서 사용하는 Embedding은 다음과 같다.

```text
Dense Vector
1024 dimensions
L2 Normalize
float32
```

Embedding 단계의 핵심 목적은 다음 두 가지다.

```text
문서 Chunk
→ Dense Vector 생성

사용자 Query
→ Dense Vector 생성
```

문서와 Query가 동일한 Embedding 공간에 있어야 이후 PostgreSQL + pgvector에서 의미 기반 유사도 검색이 가능하다.

---

## 2. 실제 서비스에서의 위치

문서 처리 기준 실제 서비스 흐름은 다음과 같다.

```text
Document Worker
  ↓
Chunking
  ↓
chunks.json
  ↓
Document Worker
  ↓
EmbeddingClient
  ↓ HTTP
POST /v1/embeddings
  ↓
Embedding Service
  ↓
BAAI/bge-m3
  ↓
1024차원 Dense Vector
  ↓
Document Worker
  ↓
Embedding Artifact 저장
  ↓
Persistence
```

중요한 점은 다음과 같다.

```text
Document Worker는 BGE-M3를 직접 실행하지 않는다.
```

실제 모델 실행 책임은 `services/embedding`에 있다.

---

## 3. 실제 서비스 진입점

Embedding Service의 실제 실행 진입점은 다음 파일이다.

```text
services/embedding/main.py
```

FastAPI Application이 시작되면 lifespan에서:

```text
EmbeddingService.load_model()
```

을 호출한다.

즉 서비스 시작 시 BGE-M3를 한 번 로드하고, 이후 `/v1/embeddings` 요청에서 해당 모델을 재사용한다.

서비스 종료 시:

```text
EmbeddingService.unload_model()
```

을 호출한다.

---

## 4. 주요 코드 구조

### Service Layer

```text
services/embedding/
├── __init__.py
├── config.py
├── schemas.py
├── service.py
├── client.py
└── main.py
```

| 파일 | 역할 |
|---|---|
| `main.py` | Embedding FastAPI 서비스 실행 진입점 |
| `config.py` | 모델 경로, CUDA, Service URL 등 환경설정 |
| `schemas.py` | API Request / Response Schema |
| `service.py` | BGE-M3 Load 및 Embedding 생성 |
| `client.py` | Document Worker와 RAG가 사용하는 HTTP Client |

### 공통 Embedding Core

```text
pipeline/embedding/
├── config.py
├── models.py
├── input_loader.py
├── validator.py
├── model_loader.py
├── embedding_generator.py
├── output_writer.py
└── run_embeddings.py
```

현재 실제 서비스에서는 이 디렉터리 전체를 직접 실행하는 것이 아니라 필요한 Core 모듈만 재사용한다.

대표적으로:

```text
services/embedding/service.py
  ↓
pipeline.embedding.config
pipeline.embedding.model_loader
pipeline.embedding.embedding_generator
pipeline.embedding.models
```

를 사용한다.

---

## 5. 실제 서비스에서 `run_embeddings.py`는 사용하지 않는다

`pipeline/embedding/run_embeddings.py`는 저장소에 존재하지만 현재 실제 서비스의 Embedding 실행 진입점은 아니다.

현재 서비스 경로:

```text
Document Worker
  ↓
EmbeddingClient
  ↓
POST /v1/embeddings
  ↓
services/embedding/main.py
```

따라서 서비스 문서 처리에서:

```text
pipeline/embedding/run_embeddings.py
```

가 실행되는 것은 아니다.

이 파일은 파일 기반 독립 실행, 개발 또는 검증 용도로 존재한다.

즉 다음처럼 구분한다.

```text
실제 서비스
= services/embedding/main.py

독립 실행 / 개발 / 검증
= pipeline/embedding/run_embeddings.py
```

---

## 6. Document Worker에서의 Embedding 시작

Chunking이 끝나면 Document Worker는 생성된 `chunks.json`을 읽는다.

현재 사용 함수:

```text
pipeline.embedding.input_loader.load_chunk_document()
```

로드 후 각 Chunk에서 다음 두 값을 사용한다.

```text
id   = chunk_id
text = embedding_text
```

개념적으로:

```text
chunks.json
  ↓
load_chunk_document()
  ↓
[
  {
    "id": "chunk-001",
    "text": "임베딩할 embedding_text"
  },
  ...
]
```

이 Request를 `EmbeddingClient.embed_items()`로 전달한다.

---

## 7. 왜 `embedding_text`를 사용하는가

Chunk에는 다음 세 가지 주요 텍스트가 존재한다.

```text
content
search_text
embedding_text
```

Embedding 단계에서 실제 모델 입력으로 사용하는 것은:

```text
embedding_text
```

이다.

`embedding_text`는 Chunking 단계에서 Section 경로와 본문을 결합하여 만든 Dense Embedding용 표현이다.

예:

```text
임대조건 > 임대보증금
주택형: 26A
임대보증금: ...
월임대료: ...
```

따라서 단순 본문만 임베딩하는 것이 아니라 문서 내 위치 정보도 함께 반영한다.

---

## 8. Embedding API

실제 Embedding 생성 Endpoint:

```http
POST /v1/embeddings
```

Request 예:

```json
{
  "items": [
    {
      "id": "chunk-001",
      "text": "임대조건 > 임대보증금 ..."
    }
  ]
}
```

Response 구조:

```json
{
  "model": "BAAI/bge-m3",
  "dimension": 1024,
  "normalized": true,
  "items": [
    {
      "id": "chunk-001",
      "embedding": [...]
    }
  ]
}
```

`embedding` 배열은 실제로 1024차원이다.

---

## 9. API 입력 검증

`services/embedding/schemas.py`에서 Request를 검증한다.

### `items`

최소 한 개 이상이어야 한다.

```text
items.length >= 1
```

### `id`

다음 조건을 만족해야 한다.

```text
빈 값 금지
공백만 있는 값 금지
한 Request 내부 중복 금지
```

### `text`

다음 조건을 만족해야 한다.

```text
빈 값 금지
공백만 있는 값 금지
```

Validation 실패 시:

```text
HTTP 422
EMBEDDING_INVALID_REQUEST
```

를 반환한다.

---

## 10. Embedding Service의 모델 로드

실제 모델 로드는 다음 함수가 담당한다.

```text
pipeline/embedding/model_loader.py
load_bge_m3_model()
```

내부에서는:

```text
FlagEmbedding.BGEM3FlagModel
```

을 사용한다.

현재 기본 모델:

```text
BAAI/bge-m3
```

---

## 11. GPU / CUDA 정책

현재 기본 설정:

```text
embedding_use_fp16 = True
embedding_require_cuda = True
embedding_device_index = 0
```

즉 서비스 환경은 기본적으로 GPU 실행을 전제로 한다.

실행 시 PyTorch를 이용해:

```text
CUDA 사용 가능 여부
GPU 이름
CUDA Version
PyTorch Version
GPU Memory
```

등을 확인한다.

`embedding_require_cuda=True`인데 CUDA를 사용할 수 없으면 CPU로 자동 전환하지 않고 Model Load 오류를 발생시킨다.

---

## 12. FP16 사용

현재 기본 설정:

```text
USE_FP16 = True
```

GPU에서 BGE-M3를 실행할 때 FP16을 사용한다.

이를 통해 일반적으로 GPU Memory 사용량을 줄이고 추론 효율을 높인다.

실제 적용 여부는 CUDA 사용 가능 여부와 함께 결정된다.

---

## 13. Dense Vector만 사용

BGE-M3는 여러 표현 방식을 지원할 수 있지만 현재 서비스에서는 Dense Vector만 사용한다.

현재 `encode()` 호출:

```text
return_dense=True
return_sparse=False
return_colbert_vecs=False
```

따라서 현재 Retrieval의 의미 기반 검색에는 BGE-M3 Dense Vector를 사용한다.

---

## 14. Embedding 생성 흐름

실제 `generate_embeddings()` 내부 흐름은 다음과 같다.

```text
EmbeddingItem[]
  ↓
embedding_text 추출
  ↓
빈 Text 검증
  ↓
BGE-M3 encode()
  ↓
dense_vecs 추출
  ↓
float32 NumPy 배열 변환
  ↓
L2 Normalize
  ↓
Vector Validation
  ↓
GeneratedEmbeddings
```

---

## 15. 기본 Embedding 설정

현재 `pipeline/embedding/config.py` 기준:

```text
MODEL_NAME = BAAI/bge-m3
TEXT_FIELD = embedding_text

BATCH_SIZE = 8
MAX_LENGTH = 8192

USE_FP16 = True
REQUIRE_CUDA = True
DEVICE_INDEX = 0

NORMALIZE_EMBEDDINGS = True
```

---

## 16. Vector Dimension

현재 BGE-M3 Dense Embedding 차원은 다음과 같다.

```text
1024
```

따라서 한 Chunk는 개념적으로 다음과 같이 변환된다.

```text
embedding_text
  ↓
BGE-M3
  ↓
[0.012, -0.031, ..., 0.082]
  ↓
1024 dimensions
```

Document Worker와 Embedding Client 모두 이 1024차원 규격을 검증한다.

---

## 17. L2 Normalize

현재 Embedding은 생성 후 L2 Normalize를 적용한다.

```text
NORMALIZE_EMBEDDINGS = True
```

개념:

```text
vector
  ↓
L2 norm 계산
  ↓
vector / norm
```

결과:

```text
||vector||₂ ≈ 1
```

문서 Chunk와 사용자 Query가 동일한 Normalize 정책을 사용해야 Vector 비교가 일관되게 이루어진다.

---

## 18. Vector Validation

Embedding 생성 후 다음과 같은 기본 검증을 수행한다.

```text
Vector Shape
NaN
Infinity
0 Vector
Chunk 수와 Vector 수
```

Document Worker에서도 Embedding Service 응답을 다시 검증한다.

Expected Shape:

```text
(chunk_count, 1024)
```

예:

```text
Chunk 100개
→ vectors.shape = (100, 1024)
```

---

## 19. `EmbeddingClient`

Document Worker와 RAG는 공용 HTTP Client인 다음 클래스를 사용한다.

```text
services.embedding.client.EmbeddingClient
```

Client는 BGE-M3를 직접 실행하지 않는다.

모든 Embedding 생성 요청은:

```text
POST /v1/embeddings
```

를 통해 전달한다.

---

## 20. `embed_items()`

Document Worker는 여러 Chunk를 처리하기 위해:

```text
EmbeddingClient.embed_items()
```

를 사용한다.

입력:

```python
[
    {
        "id": "chunk-001",
        "text": "..."
    }
]
```

반환 개념:

```python
{
    "chunk-001": np.ndarray(shape=(1024,))
}
```

응답 배열의 순서에 의존하지 않고 `id`를 기준으로 결과를 매칭한다.

---

## 21. Client 응답 검증

Client는 단순히 HTTP 200만 확인하지 않는다.

현재 다음 규격을 확인한다.

```text
model == BAAI/bge-m3
dimension == 1024
normalized == true
```

각 Vector에 대해서도 다음을 확인한다.

```text
shape == (1024,)
NaN 없음
Infinity 없음
```

또한:

```text
누락 ID
중복 ID
요청하지 않은 ID
```

도 검증한다.

이를 통해 잘못된 Embedding 응답이 다음 Pipeline 단계로 넘어가는 것을 방지한다.

---

## 22. Document Worker의 Vector 재정렬

Embedding Service Response가 Request와 동일한 배열 순서라는 가정에 의존하지 않는다.

Document Worker는 다음 기준으로 Vector를 다시 정렬한다.

```text
chunk_id
```

개념:

```text
Embedding API Response
  ↓
id → vector Map
  ↓
원래 document.items의 chunk_id 순서
  ↓
np.stack()
```

최종 결과:

```text
vectors.shape
=
(chunk_count, 1024)
```

이렇게 Chunk 순서와 Vector Index의 대응을 보장한다.

---

## 23. Embedding Artifact 저장

Embedding Service에서 Vector를 반환받은 뒤 실제 문서 처리 서비스에서는 **Document Worker가 Artifact를 저장한다.**

생성 경로:

```text
05_embeddings/{hwp|hwpx}/
├── embeddings.npy
├── metadata.json
└── embedding_report.json
```

중요한 점:

```text
이 파일들이 존재한다고 해서
run_embeddings.py가 실행된 것은 아니다.
```

현재 서비스 흐름은:

```text
Embedding Service
  ↓
Vector 반환
  ↓
Document Worker
  ↓
Artifact 저장
```

이다.

---

## 24. `embeddings.npy`

실제 Dense Vector 배열을 저장한다.

형태:

```text
shape = (chunk_count, 1024)
dtype = float32
```

예:

```text
100개 Chunk
→ (100, 1024)
```

---

## 25. `metadata.json`

Vector Index와 Chunk Metadata를 연결한다.

각 Item에는 대표적으로 다음 값이 추가된다.

```text
vector_index
chunk_id
```

그리고 원래 Chunk의 Metadata도 함께 유지한다.

파일 상단에는 현재 모델 정보도 기록된다.

```text
model
├── name: BAAI/bge-m3
├── dimension: 1024
├── normalized: true
├── dtype
└── source: embedding-service
```

---

## 26. `embedding_report.json`

Embedding 실행 결과와 품질 상태를 기록한다.

대표 정보:

```text
status
document_id
announcement_id

model_name
embedding_source

chunk_count
embedding_count
embedding_dimension
embedding_dtype

normalized

nan_count
infinity_count
zero_vector_count

norm_statistics
```

현재 서비스에서 `embedding_source`는:

```text
embedding-service
```

로 기록된다.

---

## 27. Embedding Service 오류 처리

대표 오류:

### Request 오류

```text
HTTP 422
EMBEDDING_INVALID_REQUEST
```

### 모델 미로드

```text
HTTP 503
EMBEDDING_MODEL_UNAVAILABLE
```

### Embedding 생성 실패

```text
HTTP 500
EMBEDDING_GENERATION_FAILED
```

Document Worker에서 Embedding Service 호출 자체가 실패하면:

```text
DOCUMENT_EMBEDDING_SERVICE_FAILED
```

로 변환한다.

응답 Vector 구조가 잘못된 경우:

```text
DOCUMENT_EMBEDDING_RESPONSE_INVALID
```

로 처리한다.

---

## 28. Query Embedding

Embedding Service는 문서 Chunk뿐 아니라 RAG Query에도 사용된다.

RAG에서는:

```text
EmbeddingClient.embed_query()
```

를 사용한다.

실제 내부 동작:

```text
사용자 질문
  ↓
embed_query()
  ↓
embed_items([
  {
    "id": "query",
    "text": query
  }
])
  ↓
POST /v1/embeddings
  ↓
1024D Vector
```

즉 문서 Embedding과 Query Embedding이 같은 Service와 같은 모델을 사용한다.

---

## 29. Document Embedding과 Query Embedding의 일관성

Vector Search에서 가장 중요한 조건 중 하나는 문서와 Query가 같은 Embedding 공간에 존재하는 것이다.

현재 구조:

```text
Document Chunk
  ↓
BAAI/bge-m3
  ↓
Dense 1024D
  ↓
L2 Normalize


User Query
  ↓
BAAI/bge-m3
  ↓
Dense 1024D
  ↓
L2 Normalize
```

따라서 다음 규격이 동일하게 유지된다.

```text
Model
Dimension
Normalize Policy
```

---

## 30. PostgreSQL + pgvector와의 관계

역할은 다음과 같이 구분된다.

```text
BGE-M3
→ Text를 Vector로 변환

Embedding Service
→ 모델 Load / Vector 생성 / Normalize / API 제공

PostgreSQL + pgvector
→ Vector 저장
→ Vector 유사도 검색
```

즉 pgvector가 Embedding Vector를 생성하는 것은 아니다.

Embedding Service에서 이미 생성된 1024차원 Vector를 PostgreSQL에서 Vector 타입으로 다루고 검색할 수 있게 해주는 역할이다.

---

## 31. 실제 서비스와 파일 기반 독립 실행의 차이

### 실제 서비스

```text
Document Worker
  ↓
EmbeddingClient
  ↓
Embedding Service
  ↓
BGE-M3
  ↓
Vector
  ↓
Document Worker가 Artifact 저장
```

### 독립 실행 / 개발 / 검증

```text
run_embeddings.py
  ↓
chunks.json 직접 탐색
  ↓
BGE-M3 직접 Load
  ↓
Embedding 생성
  ↓
파일 저장
```

현재 운영 서비스 흐름을 이해할 때는 첫 번째 경로를 기준으로 봐야 한다.

---

## 32. 환경설정

`services/embedding/config.py`의 주요 설정:

```text
embedding_model_name
embedding_model_path

embedding_use_fp16
embedding_require_cuda
embedding_device_index

embedding_service_url
```

현재 코드의 기본값:

```text
embedding_model_name = BAAI/bge-m3
embedding_model_path = BAAI/bge-m3

embedding_use_fp16 = True
embedding_require_cuda = True
embedding_device_index = 0

embedding_service_url = http://127.0.0.1:18001
```

실제 실행 환경에서는 `.env` 또는 Docker에서 주입한 환경변수가 적용될 수 있다.

따라서 배포 환경의 실제 URL/Port는 환경변수 설정을 확인해야 한다.

---

## 33. Health Check

Embedding Service 상태 확인 Endpoint:

```http
GET /health
```

응답 예:

```json
{
  "status": "ok",
  "model_loaded": true,
  "model": "BAAI/bge-m3"
}
```

다음 두 가지를 확인할 수 있다.

```text
Embedding Service 실행 여부
BGE-M3 Load 여부
```

---

## 34. 실제 서비스 전체 흐름

```text
Chunking
  ↓
chunks.json
  ↓
Document Worker
  ↓
load_chunk_document()
  ↓
chunk_id + embedding_text
  ↓
EmbeddingClient.embed_items()
  ↓ HTTP
POST /v1/embeddings
  ↓
services/embedding/main.py
  ↓
EmbeddingService
  ↓
load_bge_m3_model()
  ↓
generate_embeddings()
  ↓
BAAI/bge-m3
  ↓
Dense 1024D
  ↓
L2 Normalize
  ↓
EmbeddingClient
  ↓
ID / Dimension / Shape 검증
  ↓
Document Worker
  ↓
Chunk 순서대로 Vector 재정렬
  ↓
embeddings.npy
metadata.json
embedding_report.json
  ↓
Persistence
```

---

## 35. 핵심 정리

현재 DDOK BOT Embedding은 다음과 같이 정리할 수 있다.

```text
실제 서비스 실행 진입점
= services/embedding/main.py

실제 모델
= BAAI/bge-m3

실제 모델 실행
= EmbeddingService

문서 Embedding 요청
= Document Worker → EmbeddingClient.embed_items()

Query Embedding 요청
= RAG → EmbeddingClient.embed_query()

API
= POST /v1/embeddings

Vector
= Dense 1024D

Normalize
= L2 Normalize

GPU
= CUDA + FP16 기본

Artifact 저장
= Document Worker

run_embeddings.py
= 현재 서비스 경로에서는 사용하지 않음
```

Embedding 단계의 핵심은 **문서 Chunk와 사용자 Query를 동일한 BGE-M3 모델과 동일한 1024차원 정규화 Vector 공간으로 변환하여 이후 pgvector 기반 유사도 검색이 가능하도록 만드는 것**이다.

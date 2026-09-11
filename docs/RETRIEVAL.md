# AI/RAG 코드리뷰 - Retrieval

## 1. Retrieval 개요

### 1.1 역할

Retrieval은 `announcement_id`와 사용자의 질문을 입력받아 관련 공고문
Chunk를 검색하고, Generation에 전달할 검색 결과를 만드는 단계이다.

현재 MVP Retrieval은 두 가지 검색 결과를 RRF로 결합하는 Hybrid Search
구조이다.

``` text
announcement_id + question
        ↓
DBRAGPipeline
        ↓
Hybrid Search
   ┌────┴─────┐
   ↓          ↓
Vector       BM25
Search       Search
   ↓          ↓
BGE-M3     PostgreSQL
Query      Active Chunk 조회
Embedding      ↓
   ↓        Okapi BM25
PostgreSQL    계산
+ pgvector
   └────┬─────┘
        ↓
       RRF
        ↓
SearchResult[]
        ↓
Generation
```

현재 MVP 실행 경로에서는 별도의 Reranker를 사용하지 않는다.

### 1.2 주요 파일

``` text
rag/
├─ retrieval/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ hybrid_search.py
│  ├─ keyword_search.py
│  ├─ models.py
│  └─ query_embedding.py
│
├─ db_pipeline.py
├─ models.py
└─ service.py
```

각 파일의 역할은 다음과 같다.

  -----------------------------------------------------------------------
  파일                                역할
  ----------------------------------- -----------------------------------
  `rag/service.py`                    `answer_question()` RAG 진입점 제공

  `rag/db_pipeline.py`                Retrieval과 Generation 실행 조율

  `rag/models.py`                     RAG 내부 공용 데이터 모델

  `retrieval/query_embedding.py`      질문 Dense Vector 생성

  `retrieval/keyword_search.py`       PostgreSQL의 Active Chunk를
                                      조회하여 Okapi BM25 Search 수행

  `retrieval/hybrid_search.py`        Vector + BM25 결과 RRF 결합

  `retrieval/models.py`               `CorpusItem`, `SearchResult` 정의

  `retrieval/config.py`               Retrieval 관련 설정
  -----------------------------------------------------------------------

> 파일명은 기존 호환을 위해 `keyword_search.py`를 유지하지만, 현재 내부
> 검색 알고리즘은 기존 PostgreSQL `ILIKE` 가중치 검색이 아니라 **Okapi
> BM25**이다.

------------------------------------------------------------------------

# 2. Retrieval 입력 및 데이터 경계

## 2.1 입력 데이터

현재 Retrieval의 직접 입력은 다음 두 값이다.

``` text
announcement_id
question
```

예:

``` text
announcement_id = 1
question = "계약금은 얼마인가요?"
```

`announcement_id`는 검색할 공고 범위를 제한하고, `question`은 Vector
Search와 BM25 Search에 사용된다.

## 2.2 Retrieval이 조회하는 데이터

현재 Retrieval은 다음 파일을 직접 읽지 않는다.

``` text
04_chunks/chunks.json

05_embeddings/embeddings.npy

05_embeddings/metadata.json
```

대신 PostgreSQL에 SQL을 실행해 검색 데이터를 조회한다.

Vector Search에서 사용하는 주요 테이블은:

``` text
system_state
announcements
chunks
chunk_sets
processing_runs
embeddings
```

이다.

BM25 Search 역시 PostgreSQL에서 선택 공고의 Active Chunk 데이터를
조회하지만, BM25 점수 자체는 SQL의 `ILIKE` 점수식으로 계산하지 않고
**Python 코드에서 Okapi BM25 공식으로 계산한다.**

따라서 Retrieval 코드에서 직접 확인되는 시작점은:

``` text
PostgreSQL + pgvector
        ↓
Retrieval
        ↓
SearchResult[]
```

이다.

현재 Retrieval 코드만으로 다음 연결은 확인되지 않는다.

``` text
05_embeddings/
      ↓
      ?
      ↓
PostgreSQL + pgvector
```

따라서 이 연결을 Retrieval의 실제 데이터 흐름으로 확정하지 않는다.

------------------------------------------------------------------------

# 3. RAG Service 및 Pipeline

## 3.1 `service.py`

RAG의 진입 함수는:

``` text
answer_question(announcement_id, question)
```

이다.

코드상 흐름은:

``` text
answer_question()
      ↓
_get_pipeline()
      ↓
DBRAGPipeline
      ↓
ask()
```

이다.

정상 처리 후 최종적으로:

``` json
{
  "answer": "...",
  "grounded": true,
  "evidence": [...]
}
```

형태의 값을 반환한다.

## 3.2 Pipeline 재사용

`_get_pipeline()`에는:

``` python
@lru_cache(maxsize=1)
```

가 적용되어 있다.

따라서 같은 Python 프로세스에서는 Pipeline을 요청마다 새로 생성하지 않고
기존 객체를 재사용한다.

``` text
첫 호출
  ↓
DBRAGPipeline 생성
  ↓
Cache

이후 호출
  ↓
기존 Pipeline 재사용
```

## 3.3 MVP 공고 제한

`service.py`는:

``` text
MVP_ANNOUNCEMENT_ID
```

환경변수를 확인한다.

설정된 값과 요청받은 `announcement_id`가 다르면 Pipeline을 실행하지
않고:

``` json
{
  "answer": "현재 MVP에서 지원하지 않는 공고입니다.",
  "grounded": false,
  "evidence": []
}
```

를 반환한다.

## 3.4 `DBRAGPipeline`

`DBRAGPipeline`은 Retrieval과 Generation의 실행을 조율한다.

``` text
question
   ↓
Hybrid Retrieval
   ↓
검색 결과 확인
   ↓
Generation
```

초기화 시 Retrieval/Generation 설정을 검증하고 Query Embedding에 사용할
BGE-M3 모델을 로드한다.

현재 BGE-M3 모델 로딩에는 Embedding 파트의 `model_loader`를 재사용한다.

``` text
rag/db_pipeline.py
        ↓ Python import
pipeline/embedding/model_loader.py
        ↓
BGE-M3
```

------------------------------------------------------------------------

# 4. Retrieval 설정

## 4.1 기본 설정

`retrieval/config.py`의 주요 기본값은 다음과 같다.

  설정               기본값
  ------------------ --------
  `vector_top_k`     20
  `bm25_top_k`       20
  `hybrid_top_k`     20
  `rrf_k`            60
  Query Batch Size   1
  Query Max Length   8192
  FP16               `True`
  CUDA 필수          `True`
  GPU Index          0

기본 Embedding 모델은:

``` text
BAAI/bge-m3
```

이며 관련 환경변수로:

``` text
EMBEDDING_MODEL_NAME
EMBEDDING_MODEL_PATH
```

가 있다.

## 4.2 `bm25_top_k`와 실제 구현

현재 `bm25_top_k`는 이름만 BM25인 설정이 아니라 **실제 BM25 검색 결과의
Top-K 개수를 제어한다.**

현재 연결은 다음과 같다.

``` text
RetrievalConfig.bm25_top_k
        ↓
DBRAGPipeline.ask()
        ↓
HybridSearchConfig.bm25_top_k
        ↓
BM25SearchConfig.top_k
        ↓
search_bm25()
```

현재 MVP를 코드 기준으로 표현하면:

``` text
Vector Search
+
BM25 Search
+
RRF
=
Hybrid Search
```

이다.

------------------------------------------------------------------------

# 5. Query Embedding

## 5.1 `query_embedding.py`

사용자 질문을 BGE-M3 Dense Vector로 변환한다.

``` text
question
   ↓
BGE-M3
   ↓
Dense Vector
   ↓
L2 Normalize
```

현재 BGE-M3 Encode 설정은:

``` text
return_dense = True
return_sparse = False
return_colbert_vecs = False
```

이다.

따라서 Sparse Vector와 ColBERT Vector는 사용하지 않는다.

## 5.2 Query Vector 검증

BGE-M3 결과의 `dense_vecs`를 NumPy `float32` 배열로 변환한다.

이후 다음을 확인한다.

``` text
Vector Shape
NaN
Infinity
Zero Vector
```

현재 `DBRAGPipeline`의 Vector Search에서는 Query Vector Dimension이:

``` text
1024
```

인지도 확인한다.

------------------------------------------------------------------------

# 6. Vector Search

## 6.1 처리 흐름

Vector Search는 다음 순서로 진행된다.

``` text
question
   ↓
BGE-M3 Query Embedding
   ↓
Query Vector
   ↓
Dimension 확인
   ↓
pgvector용 값 생성
   ↓
PostgreSQL + pgvector
   ↓
Cosine Distance
   ↓
Top-K
```

## 6.2 DB 검색 조건

현재 Vector Search에는 다음 조건이 적용된다.

``` text
요청 announcement_id

현재 Active Collection

Active ChunkSet

Active ProcessingRun

Chunk status = completed

Embedding status = completed

현재 설정된 Embedding Model

dimension = 1024

normalized = true

embedding IS NOT NULL
```

따라서 DB의 모든 Vector를 조건 없이 검색하는 구조는 아니다.

## 6.3 공고별 검색

요청받은 `announcement_id`는 SQL 조건으로 사용된다.

``` sql
WHERE a.id = :announcement_id
```

즉:

``` text
announcement_id
      ↓
Vector Search SQL
      ↓
해당 공고 범위 검색
```

구조이다.

## 6.4 Vector Similarity

현재 pgvector의 Cosine Distance 연산자:

``` text
<=>
```

를 사용한다.

Similarity는:

``` text
1 - cosine_distance
```

형태로 계산한다.

개념적으로:

``` text
1 - (
    e.embedding <=> CAST(:query_vector AS vector)
)
```

이다.

## 6.5 Vector 검색 결과

DB Row를 먼저 `CorpusItem`으로 변환한 뒤 `SearchResult`를 구성한다.

주요 Chunk 정보는:

``` text
chunk_id
document_id
announcement_id
chunk_type
section_path
title
content
search_text
source
```

등이다.

Vector 검색 결과에는 Vector Score와 Rank 등이 기록되며, Vector
Search에서 발견된 결과는:

``` text
matched_by = {"pgvector"}
```

로 표시된다.

------------------------------------------------------------------------

# 7. BM25 Search

## 7.1 `keyword_search.py`

파일명은 `keyword_search.py`이지만 현재 내부 검색 방식은 **Okapi
BM25**이다.

기존 구현에서는 PostgreSQL `ILIKE`와 직접 정의한 가중치를 이용해 Keyword
Score를 계산했지만, 현재 구현에서는 해당 방식을 제거했다.

현재 흐름은 다음과 같다.

``` text
question
   ↓
질문 정규화
   ↓
Query Token 생성
   ↓
PostgreSQL에서 선택 공고의 Active Chunk 조회
   ↓
Chunk.search_text를 BM25 Corpus로 구성
   ↓
Corpus Tokenization
   ↓
Okapi BM25 Score 계산
   ↓
BM25 Rank
   ↓
Top-K
```

## 7.2 BM25 설정

현재 기본 설정은:

``` text
top_k = 20
min_token_length = 1
k1 = 1.5
b = 0.75
```

이다.

`k1`은 Term Frequency의 영향 정도를 조절하고, `b`는 문서 길이 정규화
정도를 조절한다.

## 7.3 Query 전처리 및 Tokenization

질문과 검색 대상 텍스트는 먼저 공백을 정리하고 소문자화한다.

이후 다음 정규표현식 기반의 최소 Tokenization을 사용한다.

``` text
[0-9A-Za-z가-힣㎡%./-]+
```

따라서 숫자, 영문, 한글, `㎡`, `%`, `.`, `/`, `-` 등의 공고문 검색에
필요한 문자를 보존한다.

현재 Mecab, Okt 등의 별도 한국어 형태소 분석기는 사용하지 않는다.

## 7.4 BM25 Corpus

BM25 검색 대상은 기본적으로 Chunk의:

``` text
search_text
```

이다.

즉:

``` text
Chunk
 ├─ content
 ├─ search_text  ← BM25 기본 Corpus
 └─ ...
```

구조이다.

`search_text`가 비어 있는 예외 데이터에서는:

``` text
title + content
```

를 합쳐 Fallback Corpus로 사용한다.

따라서 기존처럼 `search_text`, `title`, `content` 각각에 별도의 SQL
가중치를 부여하지 않는다.

## 7.5 BM25 검색 범위

BM25 Search는 먼저 PostgreSQL에서 요청한 공고의 검색 가능한 Chunk 전체를
조회한다.

적용되는 주요 조건은:

``` text
요청 announcement_id

현재 Active Collection

Active ChunkSet

Active ProcessingRun

Chunk status = completed
```

이다.

따라서 Vector Search와 BM25 Search 모두 동일한 공고 범위와 활성 데이터
기준 안에서 검색한다.

## 7.6 Okapi BM25 계산

현재 BM25 구현의 IDF는 다음 형태를 사용한다.

``` text
log(
    1 +
    (N - df + 0.5)
    /
    (df + 0.5)
)
```

각 Query Token에 대한 문서 점수는 다음 개념으로 계산한다.

``` text
IDF(q)
×
tf(q,d) × (k1 + 1)
─────────────────────────────────────────
tf(q,d) + k1 × (1 - b + b × dl / avgdl)
```

여기서:

``` text
N     = 전체 검색 대상 Chunk 수
df    = 해당 Token이 등장한 Chunk 수
tf    = 현재 Chunk에서 Token 등장 횟수
dl    = 현재 Chunk 길이
avgdl = 전체 Chunk 평균 길이
```

이다.

즉 기존의 단순 문자열 포함 여부 가중치가 아니라 **Token 빈도, 희소성,
문서 길이**를 반영해 검색 순위를 계산한다.

## 7.7 BM25 검색 결과

BM25 Score가 `0`보다 큰 Chunk만 후보로 사용하고 점수가 높은 순서대로
정렬한다.

동점이면 DB Chunk ID를 기준으로 순서를 안정적으로 결정한다.

상위 결과는:

``` text
bm25_top_k
```

개만 사용한다.

BM25 단독 검색 결과는 기존 `SearchResult` 데이터 구조를 그대로 사용한다.

현재 내부적으로:

``` text
fusion_score = BM25 raw score
fusion_rank = BM25 rank
matched_by = {"bm25"}
```

로 구성한다.

`raw_metadata`에는 대표적으로:

``` text
retrieval = "bm25"
query_tokens
bm25_score
bm25_k1
bm25_b
```

등이 기록된다.

------------------------------------------------------------------------

# 8. Hybrid Search와 RRF

## 8.1 `hybrid_search.py`

Vector Search와 BM25 Search의 결과를 RRF로 결합한다.

``` text
             Query
               ↓
       ┌───────┴───────┐
       ↓               ↓
Vector Search       BM25 Search
       ↓               ↓
Vector Rank         BM25 Rank
       └───────┬───────┘
               ↓
              RRF
               ↓
        Hybrid Ranking
               ↓
             Top-K
```

## 8.2 RRF 계산

Vector Similarity Score와 BM25 Score를 직접 더하지 않고 각 검색의
**순위**를 사용한다.

현재 공식은:

``` text
1 / (rrf_k + rank)
```

이며 기본값은:

``` text
rrf_k = 60
```

이다.

Vector와 BM25의 원점수는 서로 의미와 범위가 다르기 때문에 RRF에서는
원점수 대신 각 검색 결과의 Rank를 사용한다.

## 8.3 결과 결합

Vector Search 결과는:

``` text
matched_by = {"pgvector"}
```

로 시작한다.

BM25 Search 결과는:

``` text
matched_by = {"bm25"}
```

로 시작한다.

같은 `chunk_id`가 양쪽 검색에 존재하면:

``` text
Vector RRF Score
       +
BM25 RRF Score
       ↓
최종 Fusion Score
```

로 결합한다.

이 경우:

``` text
matched_by = {"pgvector", "bm25"}
```

처럼 두 검색 경로가 함께 기록된다.

Hybrid 내부 Metadata에는:

``` text
vector_rank
bm25_rank
rrf_k
```

가 기록된다.

## 8.4 최종 정렬

결합한 결과는 `fusion_score`를 기준으로 최종 순위를 정하고:

``` text
hybrid_top_k
```

개만 반환한다.

동점 시 Vector Rank, BM25 Rank, Chunk ID 순서가 추가 정렬 기준으로
사용된다.

------------------------------------------------------------------------

# 9. Retrieval 데이터 모델

## 9.1 `CorpusItem`

검색 대상 Chunk 정보를 표현한다.

``` text
CorpusItem
├─ chunk_id
├─ document_id
├─ announcement_id
├─ chunk_type
├─ section_path
├─ title
├─ content
├─ search_text
├─ source
└─ raw_metadata
```

## 9.2 `SearchResult`

검색 결과와 점수 및 순위 정보를 표현한다.

현재 주요 정보는:

``` text
SearchResult
├─ CorpusItem
├─ vector_score / vector_rank
├─ fusion_score / fusion_rank
└─ matched_by
```

BM25 Rank 자체는 `SearchResult`의 별도 필드가 아니라 Hybrid 처리 과정 및
`raw_metadata`에서 관리된다.

`matched_by`를 통해 검색 경로를 구분할 수 있다.

``` text
{"pgvector"}

{"bm25"}

{"pgvector", "bm25"}
```

즉 **SearchResult 클래스의 기본 데이터 구조는 유지하면서 내부 Lexical
Retrieval 방식이 Keyword/ILIKE에서 BM25로 변경된 구조**이다.

## 9.3 `RetrievalResult`

`rag/models.py`에는 RAG 내부 전달용 `RetrievalResult`가 존재한다.

``` text
RetrievalResult
├─ search_result
├─ score
└─ rank
```

Retrieval 결과의 검색 점수와 순위 정보를 다른 RAG 단계에서 사용할 수
있도록 한다.

------------------------------------------------------------------------

# 10. Retrieval → Generation

## 10.1 `DBRAGPipeline.ask()`

`ask()`는 Hybrid Search를 실행하고 결과 존재 여부를 확인한다.

``` text
ask()
 ↓
Hybrid Search
 ↓
검색 결과?
 │
 ├─ 없음
 │    ↓
 │ DBRAGNoEvidenceError
 │
 └─ 있음
      ↓
   Generation
```

Retrieval과 Generation의 연결은 현재 Python 함수 호출 방식이다.

``` text
DBRAGPipeline
      ↓
Python import / call
      ↓
Generation
```

## 10.2 Reranker 사용 여부

현재 MVP 실행 경로에는 별도의 Reranker 단계가 없다.

``` text
Vector Search
      +
BM25 Search
      ↓
RRF
      ↓
Hybrid SearchResult[]
      ↓
Generation
```

따라서 Reranker는 현재 Retrieval 실행 단계에 포함하지 않는다.

## 10.3 No-Evidence 처리

Hybrid Retrieval 결과가 없으면:

``` text
DBRAGNoEvidenceError
```

가 발생한다.

`service.py`에서는 이를 처리해:

``` json
{
  "answer": "제공된 LH 공고문 근거에서 확인할 수 없습니다.",
  "grounded": false,
  "evidence": []
}
```

형태로 반환한다.

## 10.4 정상 결과와 Evidence

정상적으로 Generation까지 완료되면 최종적으로:

``` text
answer
grounded
evidence
```

형태로 반환된다.

Evidence에는 대표적으로:

``` text
chunkId
sectionTitle
content
score
```

가 포함된다.

------------------------------------------------------------------------

# 11. 다른 코드와의 연결

## 11.1 주요 호출 관계

현재 코드에서 확인되는 연결은 다음과 같다.

  ---------------------------------------------------------------------------
  호출하는 쪽       호출받는 쪽           방식              역할
  ----------------- --------------------- ----------------- -----------------
  `rag.service`     `DBRAGPipeline`       Python import     RAG 실행

  `DBRAGPipeline`   Query Embedding       Python import     질문 Vector 생성

  Query Embedding   BGE-M3                Python Library    Dense Vector 생성

  `DBRAGPipeline`   Backend DB Session    Python import     DB Session 사용

  Vector Retrieval  PostgreSQL/pgvector   SQL               Vector Search

  BM25 Retrieval    PostgreSQL            SQL               Active Chunk 조회

  BM25 Retrieval    BM25 계산 로직        Python 함수       BM25 Score 및
                                                            Rank 계산

  Hybrid Search     Vector Retrieval      Python call       Vector 검색

  Hybrid Search     BM25 Search           Python call       BM25 검색

  Hybrid Search     Backend ErrorLog      Python import     Retrieval 오류
                                                            기록

  `DBRAGPipeline`   Generation            Python import     검색 결과 전달
  ---------------------------------------------------------------------------

Backend → `rag.service`의 호출 방식은 여기서 확정하지 않는다.

## 11.2 Backend DB Session 의존성

현재 Retrieval 코드에는:

``` python
from backend.app.db.session import SessionLocal
```

직접 import가 존재한다.

현재 코드상 관계는:

``` text
RAG Retrieval
      ↓ Python import
Backend DB Session
      ↓
PostgreSQL
```

이다.

BM25 Search 역시 동일한 `SessionLocal`을 이용해 검색 대상 Chunk를
조회한다.

## 11.3 Backend ErrorLog 의존성

`hybrid_search.py`에는:

``` python
from backend.app.services.error_log_service import record_error
```

직접 import가 존재한다.

따라서:

``` text
Hybrid Retrieval
      ↓ Python import
Backend ErrorLog Service
```

관계가 있다.

여기서는 **직접 의존성이 존재한다는 사실까지만 기록**하고 이를 어떻게
변경할지는 결정하지 않는다.

------------------------------------------------------------------------

# 12. 전체 데이터 및 실행 흐름

``` text
INPUT

announcement_id
question
        │
        ▼
────────────────────────────────
          RETRIEVAL
────────────────────────────────
        │
        ├──────────────────────────┐
        │                          │
        ▼                          ▼
 QUERY EMBEDDING               BM25 SEARCH
        │                          │
      BGE-M3                    question
        │                          │
 Dense Query Vector            Token 처리
        │                          │
        ▼                          ▼
 VECTOR SEARCH               PostgreSQL
        │                    Active Chunk 조회
PostgreSQL + pgvector             │
        │                          ▼
        │                     Okapi BM25
        │                     Score / Rank
        │                          │
        └────────────┬─────────────┘
                     ▼
                    RRF
                     │
                     ▼
              Hybrid Ranking
                     │
                     ▼
               SearchResult[]
                     │
                     ▼
────────────────────────────────
          GENERATION
────────────────────────────────
```

앞 단계까지 함께 놓으면 현재 코드에서 **확인되는 범위만** 다음과 같이
나뉜다.

``` text
[Chunking]

03_structured
      ↓
Chunking
      ↓
04_chunks/chunks.json

[Embedding]

04_chunks/chunks.json
      ↓
Embedding
      ↓
05_embeddings/
├─ embeddings.npy
├─ metadata.json
└─ embedding_report.json

[확인되지 않은 연결]

05_embeddings/
      ↓
      ?
      ↓
PostgreSQL + pgvector

[Retrieval]

PostgreSQL + pgvector
      ↓
Vector Search

PostgreSQL
      ↓
Active Chunk 조회
      ↓
Okapi BM25 Search

      ↓
RRF
      ↓
SearchResult[]
      ↓
Generation
```

따라서 현재 Retrieval 코드리뷰에서 `05_embeddings → DB` 연결은 확정하지
않는다.

------------------------------------------------------------------------

## 핵심 요약

> **Retrieval은 `announcement_id`와 사용자 질문을 입력받아 BGE-M3 Query
> Embedding 기반 pgvector Vector Search와 `search_text` 기반 Okapi BM25
> Search를 수행하고, 두 검색 결과의 순위를 RRF로 결합하여 Generation에
> 전달할 `SearchResult[]`를 생성한다. 현재 MVP 실행 경로에는 별도의
> Reranker가 없다.**

### 기존 구현 대비 변경점

``` text
[기존]

Vector Search
+
PostgreSQL ILIKE Keyword Search
+
RRF

        ↓ 변경

[현재]

Vector Search
+
Okapi BM25 Search
+
RRF
```

즉 Retrieval 전체 구조와 Generation으로 전달되는 기본 `SearchResult`
구조는 유지하면서, **Lexical Retrieval 내부 알고리즘만 기존 `ILIKE` 기반
Keyword Search에서 Okapi BM25로 교체한 상태**이다.

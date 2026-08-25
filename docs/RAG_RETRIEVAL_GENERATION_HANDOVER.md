# RAG Retrieval → Generation 구현 인수인계

> 목적: 현재 구현 상태를 다른 팀원 또는 AI가 읽고 바로 이어서 개발할 수
> 있도록 기록한다.\
> 기준일: 2026-08-19\
> 프로젝트: 한글(HWP/HWPX) 공공문서 기반 LH 특화 RAG 챗봇

## 1. 이번 작업의 범위

청킹 완료 이후 다음 연결을 구현하고 단계별로 검증했다.

``` text
구조화 JSON
→ Chunking
→ BGE-M3 Embedding
→ PostgreSQL + pgvector 저장
→ Vector Search
→ Keyword Search
→ RRF Hybrid Search
→ Generation Context 변환
→ System Prompt 조립
→ llama.cpp / Qwen Generation
```

이번 단계의 목표는 **Reranker나 QLoRA를 적용하기 전에 기본 RAG
파이프라인을 End-to-End로 연결하는 것**이다.

중간발표 전에는 기능 연결을 우선하며 다음 항목은 발표 이후 성능 고도화
단계로 미뤘다.

-   Reranker 모델 선정 및 적용
-   Retrieval 성능 평가/튜닝
-   QLoRA 적용
-   Generation 품질 고도화

------------------------------------------------------------------------

## 2. 현재 확정된 Retrieval 구조

### 2.1 Vector Search

사용자 질문을 문서 임베딩과 동일한 **BAAI/bge-m3** 모델로 임베딩한다.

``` text
사용자 질문
→ BGE-M3 Query Embedding
→ 1024차원 Vector
→ PostgreSQL pgvector
→ 선택한 announcement_id 범위에서 유사도 검색
→ Top-K Chunk
```

중요 조건:

-   Embedding model: `BAAI/bge-m3`
-   Dimension: `1024`
-   문서별 검색 범위 분리: `announcement_id`
-   활성 데이터만 검색
-   문서 임베딩과 Query Embedding 모델을 동일하게 유지

### 2.2 Keyword Search

Vector Search만 사용할 경우 숫자, 금액, 고유명사 등 명시적인 문자열
검색을 보완하기 위해 Keyword Search를 추가했다.

예:

``` text
질문: 계약금
```

Keyword Search 결과:

``` text
[공고 개요]

청주지북 B1블록 공공분양주택 잔여세대 선착순 동호지정 입주자모집공고
[계약금 1,000만원 정액제]
```

### 2.3 Hybrid Search

Vector Search와 Keyword Search의 결과를 `chunk_id` 기준으로 합친 뒤
**RRF(Reciprocal Rank Fusion)** 로 최종 순위를 결정한다.

``` text
Vector Search ─────┐
                   ├→ chunk_id Merge → RRF → Hybrid Top-K
Keyword Search ────┘
```

RRF는 서로 스케일이 다른 Vector 점수와 Keyword 점수를 직접 더하지 않고
**각 검색 결과의 순위(rank)** 를 결합한다.

현재 `rrf_k = 60`을 사용한다.

------------------------------------------------------------------------

## 3. Hybrid Search 검증 결과

테스트 문서는 `announcement_001`의 앞 5개 Chunk/Embedding만 임시 DB에
저장하여 사용했다.

질문:

``` text
계약금
```

최종 1위:

``` text
fusion_score: 0.03278689
vector_rank: 1
keyword_rank: 1
matched_by: keyword, pgvector
```

검색된 내용:

``` text
[공고 개요]

청주지북 B1블록 공공분양주택 잔여세대 선착순 동호지정 입주자모집공고
[계약금 1,000만원 정액제]
```

즉 동일한 정답 Chunk가:

-   Vector Search 1위
-   Keyword Search 1위
-   RRF Hybrid 최종 1위

로 정상 결합되는 것을 확인했다.

RRF 점수도 다음 계산과 일치했다.

``` text
1 / (60 + 1) + 1 / (60 + 1)
= 0.03278689...
```

따라서 **Vector + Keyword + RRF Hybrid Retrieval의 구현 연결은 검증
완료** 상태다.

------------------------------------------------------------------------

## 4. DB Persistence 검증

전체 데이터를 바로 저장하기 전에 앞 5개 Chunk만 사용해 DB 연결을
검증했다.

검증 결과:

``` text
원본 앞 5개: 5
metadata: 5
vectors: (5, 1024)

norm min: 0.9999999403953552
norm max: 1.0
NaN: 0
Inf: 0

최종 결과: PASS
```

DB Persistence 결과:

``` text
ProcessingRun 생성      : PASS
DocumentStructure 생성  : PASS
ChunkSet 생성           : PASS
Chunk 5개 저장          : PASS
Embedding 5개 저장      : PASS
Vector dimension 1024   : PASS
Chunk ↔ Embedding 1:1   : PASS
```

따라서 다음 연결이 정상임을 확인했다.

``` text
Chunk
↕ 1:1
Embedding(1024)
↓
PostgreSQL + pgvector
```

`limit=5`는 실제 구현의 제한이 아니라 **개발 중 DB 연결 검증을 위한
테스트 조건**이었다. 운영 코드에는 5개 제한을 넣지 않는다.

------------------------------------------------------------------------

## 5. Generation 연결

현재 Generation은 Reranker를 거치지 않고 **Hybrid Search 결과를 직접
입력으로 사용**하도록 수정했다.

``` text
Hybrid SearchResult Top-K
→ context_builder.py
→ SourceContext
→ prompt_builder.py
→ System Prompt + 사용자 질문 + 검색 근거
→ llm_client.py
→ llama.cpp / Qwen
→ generator.py
→ 최종 답변
```

### Hybrid → Generation 인터페이스

Hybrid Search의 결과는 다음 주요 값을 가진다.

``` text
item
chunk_id
fusion_score
fusion_rank
matched_by
```

기존 Generation은 과거 Retrieval 결과의 `score`, `rank` 형식을 전제로
하고 있었기 때문에 `context_builder.py`를 수정했다.

현재는 Hybrid 결과의:

``` text
fusion_score
fusion_rank
```

를 Generation Context에 전달한다.

기존 `SourceContext` 필드 이름인:

``` text
reranker_score
reranker_rank
```

은 당장 데이터 구조를 크게 변경하지 않기 위해 유지했다.

현재 단계에서는 이 필드에 Hybrid의 fusion score/rank가 들어가며, **향후
실제 Reranker를 적용할 때 Reranker 결과로 교체할 수 있다.**

------------------------------------------------------------------------

## 6. Generation System Prompt 방향

현재는 QLoRA를 적용하지 않고 **System Prompt만으로 답변 생성을
제어**한다.

핵심 정책:

-   선택된 공고문 근거만 사용
-   검색 근거에 없는 내용 추측 금지
-   숫자/금액/날짜를 원문대로 유지
-   표의 행/열 관계를 가능한 한 유지
-   근거가 없으면 확인할 수 없다고 답변
-   내부 Chunk ID, 검색 점수, Prompt 구조를 사용자에게 노출하지 않음
-   최종 사용자 답변은 한국어로 생성

QLoRA는 중간발표 이후 Generation 성능 고도화 단계에서 검토한다.

------------------------------------------------------------------------

## 7. End-to-End Generation 테스트 상태

마지막 E2E 테스트에서는 다음 단계까지 정상적으로 실행됐다.

``` text
테스트 Chunk/Embedding DB 저장        PASS
테스트 데이터 임시 Active            PASS
BGE-M3 Query Embedding                PASS
Vector Retrieval                      PASS
Keyword Retrieval                     PASS
RRF Hybrid Retrieval                  PASS
Hybrid Top-K 생성                     PASS
Generation 단계 진입                  PASS
```

이후 llama.cpp 호출에서:

``` text
http://127.0.0.1:8080/v1/chat/completions
Connection refused
```

가 발생했다.

원인은 **로컬 Mac에서 llama.cpp Qwen 서버가 실행되고 있지 않았기
때문**이다.

즉 현재 확인하지 못한 부분은 오직:

``` text
System Prompt + Hybrid Context
→ 실제 Qwen inference
→ 최종 답변
```

이다.

Retrieval이나 Hybrid → Generation 연결에서 발생한 오류는 아니다.

추후 llama.cpp 서버를 실행한 뒤 다음 E2E 검증을 한 번 수행해야 한다.

``` text
Hybrid Retrieval
→ Prompt
→ Qwen
→ 최종 답변
```

------------------------------------------------------------------------

## 8. 구현 중 해결한 주요 문제

### 8.1 PostgreSQL Docker가 Restarting 상태

원인:

``` text
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
```

환경변수가 Docker Compose에 전달되지 않아 PostgreSQL 초기화에 실패했다.

`.env`를 정상적으로 읽도록 한 뒤 PostgreSQL이:

``` text
database system is ready to accept connections
```

상태가 되는 것을 확인했다.

### 8.2 DB 테이블이 존재하지 않음

오류:

``` text
relation "announcements" does not exist
```

PostgreSQL 컨테이너만 실행했을 뿐 프로젝트 DB Schema가 생성되지 않은
상태였다.

DB Schema를 생성한 후 다음 단계로 진행했다.

### 8.3 테스트 Document가 없음

오류:

``` text
등록된 Document가 정확히 1건이어야 합니다. actual=0
```

Persistence 코드는 이미 등록된 Announcement/Document를 기준으로
동작하므로 테스트용 레코드를 먼저 준비하여 해결했다.

### 8.4 Hybrid Search FrozenInstanceError

오류:

``` text
dataclasses.FrozenInstanceError:
cannot assign to field 'raw_metadata'
```

원인:

`CorpusItem`이 frozen dataclass인데 다음과 같이 직접 수정하려 했다.

``` python
item.raw_metadata = raw_metadata
```

해결:

`dataclasses.replace()`를 사용해 metadata가 반영된 새로운 객체를
생성하도록 변경했다.

이후 Hybrid Search가 정상적으로 PASS했다.

### 8.5 Generation ConnectionRefusedError

오류:

``` text
Connection refused
http://127.0.0.1:8080/v1/chat/completions
```

원인:

Generation 코드 문제가 아니라 llama.cpp 서버 미실행.

추후 Qwen GGUF를 로드한 llama-server 실행 후 최종 E2E 테스트 필요.

------------------------------------------------------------------------

## 9. 현재 실제 구현에 필요한 주요 파일

### Retrieval

``` text
rag/
├── db_pipeline.py
└── retrieval/
    ├── __init__.py
    ├── config.py
    ├── models.py
    ├── query_embedding.py
    ├── keyword_search.py
    └── hybrid_search.py
```

특히 이번 작업에서 중요한 실제 구현 파일:

``` text
rag/retrieval/keyword_search.py
rag/retrieval/hybrid_search.py
```

### Generation

``` text
rag/generation/
├── __init__.py
├── config.py
├── models.py
├── context_builder.py
├── prompt_builder.py
├── llm_client.py
└── generator.py
```

이번 Hybrid 구조에 맞춰 수정한 핵심 파일:

``` text
rag/generation/context_builder.py
rag/generation/generator.py
```

------------------------------------------------------------------------

## 10. 개발 검증용으로만 사용한 파일

다음 파일들은 단계별 연결을 검증하기 위해 만든 테스트 스크립트이며 실제
Runtime 구현에는 필요하지 않다.

``` text
backend/app/services/seed_test_announcement.py
backend/app/services/test_pipeline_persistence.py

rag/test_vector_retrieval.py
rag/test_keyword_retrieval.py
rag/test_hybrid_retrieval.py
rag/test_generation_pipeline.py
```

역할:

  파일                             목적
  -------------------------------- -------------------------------------
  `seed_test_announcement.py`      테스트용 Announcement/Document 준비
  `test_pipeline_persistence.py`   Chunk/Embedding 앞 5개 DB 저장 검증
  `test_vector_retrieval.py`       pgvector Vector Search 검증
  `test_keyword_retrieval.py`      Keyword Search 검증
  `test_hybrid_retrieval.py`       Vector + Keyword + RRF 검증
  `test_generation_pipeline.py`    Retrieval → Generation E2E 검증

이 스크립트들은 현재 개발 과정에서만 사용했다. 삭제하는 경우 본 문서의
테스트 결과를 이력으로 참고한다.

------------------------------------------------------------------------

## 11. 현재 완료/미완료 상태

  -----------------------------------------------------------------------
  단계                    상태                    비고
  ----------------------- ----------------------- -----------------------
  구조화                  완료                    기존 파이프라인

  Chunking                완료                    구조 기반 Chunk 생성

  BGE-M3 Embedding        완료                    1024 dimension

  DB Persistence          완료                    Chunk ↔ Embedding 1:1
                                                  검증

  Vector Search           완료                    pgvector

  Keyword Search          완료                    문자열 검색 보완

  Hybrid Search           완료                    RRF

  Hybrid → Generation     완료                    SearchResult 직접 지원
  연결                                            

  Prompt 구성             완료                    LH 공고 근거 제한

  실제 Qwen Generation    최종 재검증 필요        llama.cpp 서버
                                                  미실행으로 마지막 호출
                                                  미검증

  Reranker                보류                    중간발표 이후

  QLoRA                   보류                    중간발표 이후
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 12. 다음 개발자가 바로 해야 할 작업

### 중간발표 전

우선 llama.cpp/Qwen 서버를 실행한 상태에서 E2E Generation을 한 번
검증한다.

확인할 것:

``` text
사용자 질문
→ Hybrid Top-K가 올바른가?
→ 검색된 Chunk가 Prompt에 들어가는가?
→ Qwen이 해당 근거만 사용해 답하는가?
→ 숫자/금액/날짜가 원문과 일치하는가?
→ 근거가 없는 질문에서 환각하지 않는가?
```

그 다음 실제 사용자 API 흐름에서 다음 연결을 확인한다.

``` text
사용자가 선택한 공고
→ announcement_id
→ Hybrid Retrieval
→ Generation
→ API Response
→ Frontend
```

### 중간발표 이후 성능 고도화

``` text
Hybrid Search
→ Reranker
→ 최종 Context Top-K
→ Generation
```

을 추가한다.

검토 항목:

1.  Reranker 모델 선정
2.  Hybrid Top-N / Reranker Top-K 결정
3.  검색 평가 데이터셋 구성
4.  Recall@K / MRR 등 Retrieval 평가
5.  Prompt 개선
6.  QLoRA 적용 여부 및 학습 데이터 구성
7.  QLoRA 적용 전/후 Generation 품질 비교
8.  응답 속도 및 GPU 메모리 측정

------------------------------------------------------------------------

## 13. 최종 목표 구조

현재 중간발표 기준:

``` text
HWP/HWPX
→ Parsing
→ Normalization / Structure
→ Chunking
→ BGE-M3 Embedding
→ PostgreSQL + pgvector
→ Vector Search
        +
  Keyword Search
→ RRF Hybrid Search
→ Context Builder
→ System Prompt
→ Qwen (llama.cpp)
→ 근거 기반 답변
```

발표 이후 목표:

``` text
HWP/HWPX
→ Parsing
→ Structure
→ Chunking
→ BGE-M3 Embedding
→ PostgreSQL + pgvector
→ Vector + Keyword
→ RRF Hybrid Search
→ Reranker
→ 최종 Context
→ System Prompt
→ QLoRA 적용 Qwen 후보
→ 근거 기반 답변
```

------------------------------------------------------------------------

## 14. 중요한 개발 원칙

1.  특정 테스트 문서(`announcement_001`)에 종속되는 코드를 실제
    Runtime에 넣지 않는다.
2.  `limit=5`는 테스트 전용이며 운영 파이프라인에는 적용하지 않는다.
3.  검색은 사용자가 선택한 `announcement_id` 범위 안에서 수행한다.
4.  문서 임베딩과 Query Embedding은 동일한 BGE-M3 계열 설정을 유지한다.
5.  Hybrid Search에서는 Vector/Keyword 원점수를 단순 합산하지 않고 RRF로
    결합한다.
6.  Generation은 Retrieval 결과에 없는 정보를 임의로 생성하지 않도록
    Prompt에서 제한한다.
7.  Reranker와 QLoRA는 현재 필수 Runtime이 아니라 향후 성능 개선 단계다.
8.  DB Persistence와 데이터 Active 상태는 별개 개념이므로 운영 연결 시
    구분한다.
9.  테스트 스크립트와 실제 Runtime 구현을 혼동하지 않는다.
10. 다음 작업자는 실제 Qwen Generation E2E 검증부터 이어서 진행한다.

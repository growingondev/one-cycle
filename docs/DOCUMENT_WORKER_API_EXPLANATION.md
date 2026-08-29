# Document Worker API 구현 설명

> 이 문서는 OneCycle/DDOKBOT의 **Document Worker 서비스가 왜 분리되었고, 현재 어디까지 구현되어 있으며, 전체 시스템에서 어떤 역할을 담당하는지**를 설명합니다.
>
> 처음 코드를 보는 팀원도 이 문서만 읽고 다음 내용을 이해할 수 있도록 작성했습니다.
>
> - Document Worker가 왜 필요한지
> - 기존 MVP 구조와 현재 API 분리 구조의 차이
> - 전체 서비스 구조에서 Document Worker의 위치
> - Backend / Document Worker / Embedding Service / RAG Service의 책임 범위
> - 문서 한 건이 실제로 어떤 순서로 처리되는지
> - 어떤 파일과 API가 연결되어 있는지
> - 현재 구현이 어디까지 완료되었는지
> - AWS에서 어떤 방식으로 검증했는지
> - 이후 Backend에서 무엇을 연결해야 하는지

---

# 1. 먼저 전체 구조부터 보기

현재 OneCycle은 기능을 하나의 Python 프로세스 안에서 모두 실행하는 구조가 아니라, 역할별 서비스를 분리하는 방향으로 변경하고 있다.

전체 구조를 가장 단순하게 보면 다음과 같다.

```text
사용자
  ↓
Frontend
  ↓
Backend API
  ├───────────────────────────────┐
  │                               │
  ↓                               ↓
Document Worker              RAG Service
  │                               │
  │                               ├─ Retrieval
  │                               ├─ Query Embedding
  │                               └─ LLM Generation
  │
  ├─ Parser
  ├─ Normalizer
  ├─ Structure / Verification
  ├─ Chunking
  ├─ Embedding Service 호출
  └─ Key Information Extraction
           │
           ↓
     Embedding Service
           │
           ↓
        BGE-M3
```

각 서비스의 역할을 한 문장으로 정리하면 다음과 같다.

```text
Backend
= 서비스 상태와 DB를 관리하는 중심 서버

Document Worker
= HWP/HWPX 문서를 실제로 처리하는 서버

Embedding Service
= BGE-M3 임베딩만 생성하는 서버

RAG Service
= DB에서 관련 문서를 검색하고 LLM 답변을 생성하는 서버
```

즉 Document Worker는 **문서가 들어왔을 때 검색 가능한 데이터로 바꾸는 전처리 서비스**라고 보면 된다.

---

# 2. 왜 Document Worker를 따로 만들었는가

## 기존 MVP 구조

기존 DDOKBOT MVP에서는 Backend, 문서처리, RAG 코드가 같은 Python 실행 환경 안에서 직접 연결되어 있었다.

예를 들어 Backend가 문서를 처리해야 하면 다음과 같은 구조였다.

```text
Backend
  ↓ Python import / 함수 호출
pipeline/document_processor.py
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
DB 저장
```

이 구조에서는 한 함수 안에서 다음 작업이 같이 이루어질 수 있었다.

```text
Document Context 조회
문서 처리
Embedding
DB Persistence
Key Information 저장
ProcessingRun 관리
```

초기 MVP를 빠르게 만드는 데는 편하지만 서비스 분리를 시작하면 문제가 생긴다.

Backend와 문서처리가 서로 다른 Container에서 동작하면 Backend에서 다음과 같이 직접 import할 수 없기 때문이다.

```python
from pipeline.document_processor import process_document
```

서로 다른 Container는 별도 프로세스이므로 HTTP와 같은 네트워크 통신이 필요하다.

---

# 3. API 분리 이후 구조

그래서 기존 `pipeline` 코드를 버리거나 다시 작성한 것이 아니라, 그 앞에 **Document Worker라는 HTTP Service Layer를 추가**했다.

```text
기존

Backend
  ↓ 직접 함수 호출
pipeline


현재

Backend
  ↓ HTTP
Document Worker
  ↓ 내부 Python 호출
pipeline
```

쉽게 표현하면 다음과 같다.

```text
pipeline
= 실제 문서를 처리하는 엔진

Document Worker
= Backend가 그 엔진을 HTTP로 실행할 수 있게 만든 서버
```

따라서 이번 API 분리 작업은 Parser, Normalizer, Structure, Chunking의 품질 로직을 새로 작성한 작업이 아니다.

기존 문서처리 코드를 최대한 그대로 사용하면서 **서비스 간 연결 방식만 직접 호출 → HTTP 방식으로 변경한 작업**이다.

---

# 4. 현재 서비스별 책임 범위

서비스 분리에서 가장 중요한 부분은 **어떤 서비스가 무엇을 책임지는지 명확히 하는 것**이다.

## 4.1 Backend

Backend는 DB와 서비스 상태를 관리한다.

```text
Backend 책임

- Document DB Context 조회
- Document Worker 호출
- Worker Response 검증
- Artifact 검증
- DB Transaction
- ProcessingRun 생성 / 실패 / 완료 상태 관리
- Chunk DB 저장
- Embedding DB 저장
- Key Information DB 저장
- 활성 ProcessingRun 관리
- 사용자 API 제공
```

Backend는 HWP/HWPX 파일 내부를 직접 파싱하지 않는다.

---

## 4.2 Document Worker

Document Worker는 실제 문서를 처리한다.

```text
Document Worker 책임

- 원본 파일 존재 확인
- 실제 HWP/HWPX 형식 판별
- Parser 실행
- Normalizer 실행
- Structure 실행
- Structure Verification 확인
- Chunking 실행
- Embedding Service 호출
- Embedding 응답 검증
- Embedding Artifact 저장
- Key Information Extraction
- 최종 처리 결과 반환
```

Document Worker는 Backend DB를 직접 조회하거나 갱신하지 않는다.

즉 Worker는 다음 질문에 답하는 서비스다.

```text
"이 문서를 처리해서
검색 가능한 Chunk와 Embedding,
그리고 핵심정보를 만들어줘."
```

---

## 4.3 Embedding Service

Embedding Service는 BGE-M3 모델 실행만 담당한다.

```text
Embedding Service 책임

- BGE-M3 모델 로드
- GPU 사용
- Dense Embedding 생성
- L2 Normalization
- Embedding API 제공
```

현재 계약:

```text
Model      : BAAI/bge-m3
Dimension  : 1024
Normalized : true
dtype      : float32
```

Document Worker와 RAG Service가 둘 다 같은 Embedding Service를 사용한다.

```text
Document Worker ─┐
                 ├─→ Embedding Service → BGE-M3
RAG Service ─────┘
```

이 구조를 사용하면 Worker와 RAG가 각각 BGE-M3 모델을 따로 로드할 필요가 없다.

---

## 4.4 RAG Service

RAG Service는 이미 처리되어 DB에 저장된 Chunk를 대상으로 검색하고 답변을 생성한다.

```text
RAG Service 책임

- 사용자 질문 수신
- Query Embedding 생성
- Vector Search
- Keyword Search
- Hybrid Search
- Retrieval 결과 구성
- LLM Generation
```

Document Worker는 RAG 답변을 생성하지 않는다.

Document Worker는 **RAG가 사용할 데이터를 만드는 쪽**, RAG Service는 **그 데이터를 검색하고 답변하는 쪽**이다.

---

# 5. 전체 문서 처리 흐름

Backend가 문서 한 건을 처리한다고 가정하면 현재 흐름은 다음과 같다.

```text
1. Backend
   ↓
2. POST /v1/documents/{document_id}/process
   ↓
3. Document Worker
   ↓
4. 원본 파일 검증
   ↓
5. 실제 HWP/HWPX 형식 판별
   ↓
6. Parser
   ↓
7. Normalizer
   ↓
8. Structure
   ↓
9. Verification
   ↓
10. Chunking
   ↓
11. Embedding Service HTTP 호출
   ↓
12. BGE-M3 Embedding 생성
   ↓
13. Embedding Artifact 저장
   ↓
14. Key Information Extraction
   ↓
15. DocumentProcessResponse 생성
   ↓
16. HTTP 200 completed
   ↓
17. Backend
   ↓
18. DB Persistence / ProcessingRun 처리
```

현재 Document Worker 내부 구현은 **16번까지 완료**되어 있다.

Backend에서 실제 DB Persistence까지 연결하는 작업은 별도 Backend 통합 범위다.

---

# 6. Document Worker API

## Endpoint

```http
POST /v1/documents/{document_id}/process
```

예:

```http
POST /v1/documents/1/process
```

`document_id`는 URL Path Parameter로 전달한다.

---

## Request Body

```json
{
  "announcement_id": 1,
  "announcement_key": "announcement_001",
  "source": {
    "filename": "announcement.hwpx",
    "format": "hwpx",
    "storage_path": "/data/documents/announcement_001/announcement.hwpx"
  }
}
```

각 값의 의미는 다음과 같다.

| 필드 | 설명 |
|---|---|
| `document_id` | 처리 대상 Document ID. URL에 포함 |
| `announcement_id` | 해당 문서가 속한 공고 ID |
| `announcement_key` | Artifact 경로 등에 사용하는 공고 식별자 |
| `source.filename` | 원본 파일명 |
| `source.format` | Backend가 알고 있는 형식 (`hwp` / `hwpx`) |
| `source.storage_path` | Worker가 실제로 접근할 원본 파일 경로 |

Docker에서는 Backend와 Worker가 Shared Volume을 사용해 같은 파일 경로를 바라보는 구조를 전제로 한다.

---

# 7. 단계별 처리 과정

## 7.1 원본 파일 검증

처리를 시작하면 가장 먼저 `storage_path`에 실제 파일이 존재하는지 확인한다.

파일이 없는데 Parser를 먼저 실행하면 오류 원인이 경로 문제인지 Parser 문제인지 구분하기 어려워지기 때문이다.

파일이 없으면 다음과 같은 형태로 오류를 반환한다.

```json
{
  "error": {
    "code": "DOCUMENT_SOURCE_NOT_FOUND",
    "message": "원본 문서 파일을 찾을 수 없습니다."
  }
}
```

---

## 7.2 실제 HWP/HWPX 형식 판별

확장자만 보고 Parser를 선택하지 않는다.

사용 코드:

```text
pipeline/parser/format_detector.py
```

핵심 함수:

```python
detect_actual_document_format()
```

판별 값:

```text
hwp
hwpx
unknown
```

예를 들어 파일명은 `.hwp`지만 실제 내부 구조가 HWPX라면 잘못된 Parser를 실행하지 않도록 여기서 차단한다.

Backend가 전달한 `source.format`과 실제 판별 형식이 일치하는지도 확인한다.

---

## 7.3 Parser

실제 형식에 따라 기존 Parser를 실행한다.

```text
HWP
pipeline/parser/hwp_parser.py

HWPX
pipeline/parser/hwpx_parser.py
```

관련 라이브러리:

```text
HWP  : hwplib-1.1.10.jar
HWPX : hwpxlib-1.0.8.jar
```

출력 예:

```text
outputs/announcement_001/document_1/01_parsed/hwpx.json
```

Worker는 subprocess가 끝났는지만 보는 것이 아니라 실제 결과 파일 생성 여부도 확인한다.

---

## 7.4 Normalizer

Parser JSON을 후속 처리에 적합하도록 정규화한다.

사용 코드:

```text
pipeline/normalizer/document_normalizer.py
```

입력:

```text
01_parsed/<format>.json
```

출력:

```text
02_normalized/<format>.json
```

여기서는 기존 문서처리에서 사용하던 문자, 날짜, 금액, 특수표현 등의 정규화 로직을 그대로 재사용한다.

---

## 7.5 Structure / Verification

사용 코드:

```text
pipeline/structure/run_structure.py
```

Structure에서는 다음 작업이 이루어진다.

```text
문서 계층 구조 생성
Section 구성
Domain 분류
표 구조화
값 타입 정규화
Structure 검증
```

후속 단계에서 중요한 결과는 다음 두 파일이다.

```text
step4-1_value_normalized.json
step4-3_verification.json
```

경로:

```text
03_structured/<format>/
├─ step4-1_value_normalized.json
├─ step4-2_value_validation.json
├─ step4-3_verification.json
└─ 기타 중간 산출물
```

`step4-1_value_normalized.json`은 Chunking과 Key Information Extraction에 사용된다.

`step4-3_verification.json`은 Structure 결과가 정상인지 확인하는 파일이다.

---

## 7.6 Chunking

사용 코드:

```text
pipeline/chunking/run_chunking.py
```

입력:

```text
03_structured/<format>/step4-1_value_normalized.json
```

출력:

```text
04_chunks/<format>/chunks.json
```

Chunking은 하나의 긴 공고문을 RAG Retrieval에서 사용할 수 있는 검색 단위로 나눈다.

각 Chunk에는 대표적으로 다음 정보가 포함된다.

```text
chunk_id
embedding_text
document_id
announcement_id
chunk_order
chunk_type
section 정보
검색용 텍스트
source 정보
```

`embedding_text`는 다음 Embedding Service에 전달하는 실제 텍스트다.

---

# 8. 왜 Embedding을 Worker에서 직접 실행하지 않는가

초기 코드에는 Worker에서 직접 BGE-M3를 실행할 수 있는 기존 Embedding Pipeline이 존재한다.

하지만 서비스 분리 이후에는 다음 방식으로 사용하지 않는다.

```text
Document Worker
→ pipeline/embedding/run_embeddings.py
→ BGE-M3 직접 로드
```

대신 다음 구조를 사용한다.

```text
Document Worker
   ↓ HTTP
Embedding Service
   ↓
BGE-M3
```

이유는 BGE-M3가 GPU 자원을 사용하는 모델이기 때문이다.

Worker와 RAG가 각각 모델을 로드하면 다음 문제가 생길 수 있다.

```text
GPU 메모리 중복 사용
모델 로딩 시간 증가
서비스별 모델 버전 불일치
자원 관리 복잡도 증가
```

그래서 Embedding 모델은 Embedding Service 한 곳에서만 실행한다.

---

# 9. Document Worker → Embedding Service 연동

사용 파일:

```text
services/embedding/client.py
pipeline/embedding/input_loader.py
document_worker/service.py
```

Chunking이 끝나면 Worker는 `chunks.json`을 읽는다.

`load_chunk_document()`를 통해 각 Chunk에서 다음 값을 가져온다.

```text
chunk_id
embedding_text
metadata
```

Worker는 이를 Embedding API Request로 변환한다.

```json
{
  "items": [
    {
      "id": "chunk-001",
      "text": "임베딩할 문장"
    }
  ]
}
```

호출 Endpoint:

```http
POST /v1/embeddings
```

Embedding Service 응답:

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

---

# 10. 왜 응답 순서가 아니라 ID로 Vector를 연결하는가

중요한 구현 포인트다.

Worker는 다음처럼 단순히 배열 순서만 믿지 않는다.

```text
요청 0번째 Chunk
=
응답 0번째 Vector
```

대신 다음 기준으로 연결한다.

```text
request chunk_id
      ↕
response item.id
```

예:

```text
Request

chunk-001
chunk-002
chunk-003


Response 순서가

chunk-003
chunk-001
chunk-002

로 와도

ID를 보고 다시 올바른 순서로 연결한다.
```

이를 통해 HTTP Service가 내부적으로 처리 순서를 변경하더라도 Chunk와 Embedding의 관계가 깨지지 않는다.

---

# 11. Embedding Client에서 검증하는 것

`services/embedding/client.py`는 단순히 HTTP 요청만 보내는 코드가 아니다.

다음 항목을 검증한다.

```text
Request ID 중복 여부
Response ID 중복 여부

요청했는데 응답에 없는 ID
요청하지 않았는데 응답에 추가된 ID

model == BAAI/bge-m3
dimension == 1024
normalized == true

Vector shape == (1024,)
NaN 존재 여부
Infinity 존재 여부

HTTP timeout
Connection error
잘못된 JSON Response
```

이 검증을 하는 이유는 잘못된 Vector가 DB까지 저장되는 것을 최대한 앞단에서 막기 위해서다.

---

# 12. Embedding Artifact

Embedding Service에서 Vector를 받으면 Worker가 Artifact를 생성한다.

현재 전체 Artifact 구조는 다음과 같다.

```text
outputs/
└─ <announcement_key>/
   └─ document_<document_id>/
      ├─ 01_parsed/
      │  └─ <format>.json
      │
      ├─ 02_normalized/
      │  └─ <format>.json
      │
      ├─ 03_structured/
      │  └─ <format>/
      │     ├─ step4-1_value_normalized.json
      │     ├─ step4-2_value_validation.json
      │     ├─ step4-3_verification.json
      │     └─ 기타 중간 산출물
      │
      ├─ 04_chunks/
      │  └─ <format>/
      │     └─ chunks.json
      │
      └─ 05_embeddings/
         └─ <format>/
            ├─ embeddings.npy
            ├─ metadata.json
            └─ embedding_report.json
```

## `embeddings.npy`

실제 Dense Vector 배열이다.

AWS 테스트 결과:

```text
shape  : (291, 1024)
dtype  : float32
finite : True
```

즉 291개 Chunk에 대해 각각 1024차원 Vector가 정상 생성되었다.

---

## `metadata.json`

Embedding과 Chunk를 연결하기 위한 metadata를 저장한다.

대표 정보:

```text
vector_index
chunk_id
document_id
announcement_id
chunk_order
chunk_type
section 관련 정보
source 관련 정보
```

---

## `embedding_report.json`

Embedding 생성 결과를 검증하기 위한 보고 파일이다.

대표 정보:

```text
model
dimension
normalized
dtype
chunk_count
embedding_count
NaN count
Infinity count
Zero vector count
Vector norm 통계
```

---

# 13. Key Information Extraction

Embedding Artifact까지 저장한 뒤 핵심정보를 추출한다.

사용 코드:

```text
pipeline/key_information_extractor.py
```

호출 형태:

```python
extract_key_information(
    structure_path=...,
    verification_path=...,
    context=...,
)
```

입력은 Embedding이 아니라 **Structure 결과**다.

```text
step4-1_value_normalized.json
step4-3_verification.json
```

즉 흐름상 Embedding 뒤에서 실행하지만, 핵심정보 추출 자체는 Structure 데이터를 읽는다.

---

# 14. Key Information 7개 필드

현재 Backend 계약에서 사용하는 핵심정보는 다음 7개다.

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

의미는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `application_period` | 신청/접수 기간 |
| `eligibility` | 신청자격 / 입주자격 |
| `supply_information` | 공급대상, 주택형, 공급호수, 임대조건 등 |
| `income_asset_criteria` | 소득·자산 기준 |
| `required_documents` | 제출/구비/증빙 서류 |
| `winner_announcement` | 당첨자 또는 예비입주자 발표 |
| `contact_information` | 문의처, 전화번호, 주택전시관 등 |

Extractor는 Structure 단계에서 만든 다음 정보를 우선 활용한다.

```text
domain.category
domain.topic
domain.confidence
```

그리고 Domain 정보만으로 부족한 경우 다음을 보조적으로 사용한다.

```text
Section 제목
본문 Keyword
표 Key / Value
정규화 Entity
날짜
전화번호
```

---

# 15. extracted와 not_found의 차이

Key Information 필드는 모두 무조건 어떤 값을 만들어내는 구조가 아니다.

원문에 해당 정보가 없거나 현재 규칙으로 찾지 못하면 다음처럼 반환될 수 있다.

```json
{
  "status": "not_found"
}
```

이것은 Worker 실패가 아니다.

예를 들어:

```text
application_period : not_found
```

이면

```text
Document Worker가 실패했다
```

는 의미가 아니라,

```text
문서처리는 성공했지만
application_period에 해당하는 정보를
Extractor가 찾지 못했다
```

는 의미다.

따라서 핵심정보 일부가 `not_found`여도 Worker 전체는 `200 completed`가 될 수 있다.

---

# 16. Key Information 검증

Document Worker는 Extractor가 반환한 결과를 그대로 믿지 않고 최소 계약을 다시 확인한다.

```text
7개 필드가 모두 존재하는가?
각 필드가 dict 형태인가?
```

다음과 같은 경우는 정상 완료로 처리하지 않는다.

```text
필드 자체가 누락됨
필드 타입이 잘못됨
Extractor 실행 중 예외 발생
Verification이 pass가 아님
```

이 경우 대표적으로 다음 오류를 사용한다.

```text
DOCUMENT_KEY_INFORMATION_FAILED
```

---

# 17. 최종 성공 Response

모든 처리가 끝나면 Worker는 더 이상 `501 Not Implemented`를 반환하지 않는다.

현재 정상 응답은:

```text
HTTP 200
status = completed
```

이다.

예:

```json
{
  "document_id": 1,
  "announcement_id": 1,
  "announcement_key": "announcement_001",
  "status": "completed",
  "document_format": "hwpx",
  "output_path": "...",
  "summary": {
    "chunk_count": 291,
    "embedding_count": 291
  },
  "key_information": {
    "application_period": {},
    "eligibility": {},
    "supply_information": {},
    "income_asset_criteria": {},
    "required_documents": {},
    "winner_announcement": {},
    "contact_information": {}
  }
}
```

`chunk_count`와 `embedding_count`를 함께 반환하는 이유는 Chunk와 Vector 개수가 일치하는지 Backend에서도 확인할 수 있게 하기 위해서다.

---

# 18. 이전 501 상태는 무엇이었는가

개발 도중에는 일부러 `501 Not Implemented`를 사용했다.

## 1차 상태

처음에는 Chunking까지만 완료되어 있었다.

```text
Parser
→ Normalizer
→ Structure
→ Chunking
→ 501
```

이유:

```text
Embedding Service 연동 미완료
Key Information 연동 미완료
```

---

## 2차 상태

Embedding API를 연결한 뒤에는 다음까지 완료됐다.

```text
Parser
→ Normalizer
→ Structure
→ Chunking
→ Embedding API
→ Artifact
→ 501
```

당시 응답 메시지:

```text
Document processing through embedding completed successfully.
Key information extraction integration is pending.
```

---

## 현재 상태

Key Information Extraction까지 연결했기 때문에 임시 `NotImplementedError`를 제거했다.

```text
Parser
→ Normalizer
→ Structure
→ Chunking
→ Embedding API
→ Artifact
→ Key Information
→ 200 completed
```

---

# 19. 실제 AWS 통합 테스트 결과

테스트 문서:

```text
tests/fixtures/documents/announcement_001/
(계약금1,000)청주지북_B1블록_공공분양주택_잔여세대_추가_입주자모집(선착순_동호지정)_공고문.hwpx
```

Embedding Service:

```text
127.0.0.1:18001
```

Document Worker:

```text
127.0.0.1:18003
```

실제 요청 한 번으로 전체 Pipeline을 실행했다.

최종 결과:

```text
HTTP Status      : 200
Worker Status    : completed

Chunk Count      : 291
Embedding Count  : 291

Embedding Shape  : (291, 1024)
Embedding dtype  : float32
Finite Check     : True
```

Key Information:

```text
application_period     : not_found
eligibility            : extracted
supply_information     : extracted
income_asset_criteria  : extracted
required_documents     : extracted
winner_announcement    : not_found
contact_information    : extracted
```

따라서 AWS에서 다음 전체 흐름이 실제로 동작함을 확인했다.

```text
HWPX
→ Parser
→ Normalizer
→ Structure
→ Verification
→ Chunking
→ Embedding Service HTTP
→ BGE-M3
→ Embedding Artifact
→ Key Information Extraction
→ HTTP 200 completed
```

`application_period`, `winner_announcement`의 `not_found`는 API 연결 실패가 아니라 추출 결과다.

---

# 20. 현재 사용 포트

AWS 테스트 기준:

| 서비스 | 주소 |
|---|---|
| Embedding Service | `127.0.0.1:18001` |
| RAG Service | `127.0.0.1:18002` |
| Document Worker | `127.0.0.1:18003` |
| llama.cpp | `127.0.0.1:8080` |

Document Worker는 환경변수로 Embedding Service 주소를 받는다.

```bash
export EMBEDDING_SERVICE_URL=http://127.0.0.1:18001
```

Worker 실행 예:

```bash
python -m uvicorn document_worker.main:app \
  --host 127.0.0.1 \
  --port 18003
```

Docker 환경에서는 `127.0.0.1` 대신 Docker service name을 사용해야 한다.

예:

```text
http://embedding:18001
```

---

# 21. 관련 코드 위치

## Document Worker

```text
document_worker/main.py
document_worker/api/routes.py
document_worker/api/schemas.py
document_worker/service.py
```

### `main.py`

FastAPI 애플리케이션 생성.

### `api/routes.py`

Endpoint 정의 및 HTTP Error 변환.

### `api/schemas.py`

Request / Response 계약 정의.

### `service.py`

전체 문서 처리 순서를 실제로 연결하는 핵심 파일.

---

## 기존 Pipeline

```text
pipeline/parser/
pipeline/normalizer/
pipeline/structure/
pipeline/chunking/
pipeline/key_information_extractor.py
```

이 코드는 Document Worker가 내부에서 재사용한다.

---

## Embedding 관련

```text
services/embedding/main.py
services/embedding/service.py
services/embedding/schemas.py
services/embedding/client.py
pipeline/embedding/input_loader.py
```

`services/embedding/client.py`는 Worker와 Embedding Service 사이의 HTTP Client다.

`pipeline/embedding/input_loader.py`는 `chunks.json`을 읽어 임베딩 요청에 필요한 Chunk 데이터를 구성한다.

---

# 22. 기존 `pipeline/document_processor.py`와 현재 구조의 차이

기존:

```text
pipeline/document_processor.py

DB Context 조회
↓
문서처리
↓
Embedding
↓
DB 저장
↓
Key Information
↓
ProcessingRun
```

현재:

```text
Backend

DB Context / ProcessingRun
        ↓ HTTP
Document Worker

문서처리
↓
Embedding Service 호출
↓
Key Information
        ↓ Response
Backend

DB Persistence
↓
ProcessingRun 활성화
```

즉 기존 하나의 큰 실행 흐름을 서비스 책임에 맞게 나눈 것이다.

---

# 23. 현재 작업 범위에서 완료된 것

현재 Document Worker 관련 작업은 다음까지 완료됐다.

```text
[완료] FastAPI Document Worker 생성
[완료] POST /v1/documents/{document_id}/process
[완료] Request Schema
[완료] Response Schema

[완료] 원본 파일 검증
[완료] 실제 HWP/HWPX 형식 판별
[완료] Parser 연결
[완료] Normalizer 연결
[완료] Structure 연결
[완료] Verification 확인
[완료] Chunking 연결

[완료] Embedding Service HTTP Client
[완료] Worker → Embedding API 연동
[완료] chunk_id 기반 Vector 매칭
[완료] Embedding 응답 검증
[완료] Embedding Artifact 저장

[완료] Key Information Extraction 연동
[완료] 7개 필드 계약 검증

[완료] 최종 DocumentProcessResponse
[완료] HTTP 200 completed
[완료] AWS 실제 HWPX 통합 테스트
```

즉 **Document Worker 내부 처리 흐름 자체는 현재 완성된 상태**다.

---

# 24. 아직 남은 작업

현재 남은 핵심 작업은 Document Worker 내부 로직이 아니라 **전체 서비스 Runtime 통합** 쪽이다.

가장 중요한 다음 흐름은 다음과 같다.

```text
Backend
  ↓
ProcessingRun 생성
  ↓
Document Worker HTTP 호출
  ↓
200 completed
  ↓
Worker Response / Artifact 검증
  ↓
Chunk DB 저장
  ↓
Embedding DB 저장
  ↓
Key Information DB 저장
  ↓
ProcessingRun 활성화
```

따라서 이후 확인해야 할 내용은 다음과 같다.

```text
Backend → Document Worker HTTP Client 연결

Worker Response와
Backend Persistence 계약 일치 여부

Docker Compose에서
Backend / Worker / Embedding Service
service name 연결

Shared Volume 경로 확인

Service timeout 정책

Embedding Service health check

여러 HWP/HWPX 문서 회귀 테스트

Key Information not_found 품질 개선

대용량 문서 Embedding batch 전략 검토
```

---

# 25. 현재 구조에서 주의할 점

## Worker는 DB에 직접 저장하지 않는다

Document Worker에서 생성한 결과를 직접 PostgreSQL에 넣는 구조로 되돌리지 않는다.

```text
Worker
= 처리

Backend
= 저장
```

이 책임 경계를 유지한다.

---

## Worker는 BGE-M3를 직접 로드하지 않는다

다음 구조로 되돌리지 않는다.

```text
Document Worker
→ BGE-M3 직접 로드
```

항상:

```text
Document Worker
→ HTTP
→ Embedding Service
```

를 사용한다.

---

## Embedding Response 순서에 의존하지 않는다

항상:

```text
chunk_id ↔ response id
```

로 매칭한다.

---

## `not_found`를 Worker 실패로 해석하지 않는다

```text
status = not_found
```

는 해당 필드를 찾지 못했다는 의미다.

전체 문서 처리 실패와 구분한다.

---

# 26. 팀원이 코드를 볼 때 추천 순서

처음 이 코드를 확인한다면 다음 순서로 보는 것이 가장 이해하기 쉽다.

```text
1. document_worker/api/schemas.py
   → Request / Response가 무엇인지 먼저 확인

2. document_worker/api/routes.py
   → 어떤 Endpoint가 service.py를 호출하는지 확인

3. document_worker/service.py
   → 전체 Pipeline 실행 순서 확인

4. pipeline/parser/
5. pipeline/normalizer/
6. pipeline/structure/
7. pipeline/chunking/
   → 실제 문서처리 세부 구현 확인

8. services/embedding/client.py
   → Worker가 Embedding Service를 어떻게 호출하는지 확인

9. services/embedding/
   → 실제 BGE-M3 API 동작 확인

10. pipeline/key_information_extractor.py
    → 핵심정보 7개가 어떻게 생성되는지 확인
```

특히 전체 흐름을 파악하려면 처음부터 Parser 내부 코드로 들어가기보다 `document_worker/service.py`를 먼저 보는 것이 좋다.

`service.py`가 각 Pipeline을 어떤 순서로 연결하는지 보여주는 중심 파일이기 때문이다.

---

# 27. 한 문장으로 정리

현재 Document Worker는

> **Backend에서 받은 HWP/HWPX 문서 한 건을 기존 문서처리 Pipeline으로 파싱·정규화·구조화·청킹한 뒤, 별도 Embedding Service를 통해 BGE-M3 Vector를 생성하고 핵심정보 7개를 추출하여 최종 `200 completed` Response를 반환하는 독립 문서처리 서비스**

이다.

현재 AWS에서 실제 HWPX 문서 기준으로 **291개 Chunk → 291개 1024차원 Embedding → Key Information Extraction → HTTP 200**까지 전체 흐름을 검증한 상태다.

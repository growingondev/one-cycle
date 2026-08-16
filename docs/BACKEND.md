# Backend / DB 코드 가이드 및 기능별 인수인계

> 기준 시점: 2026-08-16  
> 목적: **Backend / DB에서 구현한 코드의 역할을 설명하고, 다른 기능 담당자가 어떤 파일을 읽고 어디에 자기 기능을 연결해야 하는지 안내**
>
> 이 문서는 Git 작업 이력이 아니라 **현재 최종 코드의 역할, 사용 방법, 연동 지점**을 설명한다.

---

# 1. Backend / DB가 담당하는 역할

Backend / DB 코드는 Crawler, Parser, Chunking, Embedding 같은 알고리즘을 직접 구현하지 않는다.

대신 다음을 책임진다.

- 어떤 데이터를 DB에 저장할지 정의
- 저장 전 어떤 조건을 검증할지 정의
- 현재 서비스에서 사용할 정상 데이터(active)를 결정
- 사용자 / 관리자 API 제공
- 관리자 인증 및 세션 관리
- 다른 기능을 호출할 수 있는 Gateway 제공
- 기능 사이의 입력 / 출력 계약 제공
- Crawler / 문서 처리 / AI 결과를 DB에 저장

전체 역할은 다음과 같다.

```text
외부 기능에서 결과 생성
        ↓
Backend Service
        ↓
DB 검증 / 저장 / 상태 관리
        ↓
Backend API
        ↓
Frontend / RAG / 관리자 기능
```

---

# 2. 기능 영역 경계

통합 시 역할이 섞이지 않도록 아래 기준을 사용한다.

## Backend / DB

```text
API 서버
DB 모델
DB 조회 / 저장
Persistence
관리자 인증 / 세션
Collection 관리
ErrorLog 관리
외부 기능 호출 Gateway
```

## Crawler

```text
공고 수집
상세 페이지 접근
첨부파일 다운로드
Pagination
Selenium 처리
수집 실패 정보 생성
```

## 문서 처리

```text
HWP/HWPX Parsing
Normalizer
Structure
Verification
핵심정보 추출
```

## AI / RAG

```text
Chunking
Embedding
Vector Search
Retrieval
Prompt
LLM Response
```

## Frontend

```text
사용자 UI
관리자 UI
Backend API 호출
세션 Cookie 사용
```

---

# 3. 기능별 필독 Backend 파일

전체 코드를 처음부터 읽을 필요는 없다.

| 기능 영역 | 우선 확인할 파일 | 확인 목적 |
|---|---|---|
| Crawler | `collection_service.py` → `collection_run.py` → `announcement.py` → `document.py` → `pipeline_gateway.py` | 어떤 결과를 반환하고 DB에 어떻게 저장되는지 확인 |
| 문서 처리 | `document.py` → `processing_run.py` → `document_structure.py` → `pipeline_persistence.py` → `pipeline_gateway.py` | `document_id` 기반 처리와 Structure / Verification 결과 연결 방식 확인 |
| AI / RAG | `chunk_set.py` → `chunk.py` → `embedding.py` → `system_state.py` → `pipeline_persistence.py` → `collection_publish_service.py` | Chunk / Embedding 저장과 active Collection 기준 확인 |
| 핵심정보 추출 | `key_information.py` → `key_information_service.py` | 추출 결과 저장 필드와 upsert 방식 확인 |
| Frontend | `admin.py` → `schemas/admin.py` | API Endpoint와 Request / Response 계약 확인 |

---

# 4. DB Model 코드 설명

DB 관계는 다음과 같다.

```text
CollectionRun
    ↓
Announcement
    ↓
Document
    ↓
ProcessingRun
    ├──────────────→ DocumentStructure
    ↓
ChunkSet
    ↓
Chunk
    ↓
Embedding

Announcement
    ↓
KeyInformation

SystemState
    ↓
현재 active CollectionRun

ErrorLog
    ↓
처리 실패 기록
```

---

## 4.1 `backend/app/models/collection_run.py`

### 역할

**공고 수집 1회를 하나의 실행 단위로 기록**한다.

```text
관리자 '공고 수집' 1회
→ CollectionRun 1개
```

주요 상태:

```text
running
success
partial
failed
```

주요 카운트:

```text
total_announcement_count
successful_announcement_count
failed_announcement_count
```

### 연동 시 알아야 할 점

- Crawler 결과를 저장할 때 가장 먼저 생성되는 상위 레코드다.
- Collection publish도 `collection_run_id`를 기준으로 수행한다.

---

## 4.2 `backend/app/models/announcement.py`

### 역할

LH의 **공고 1건**을 저장한다.

주요 데이터:

```text
source_announcement_id
title
region
announcement_date
publication_status
detail_url
collection_run_id
```

### 관계

```text
CollectionRun 1
    ↓
Announcement N
```

### 연동 시 알아야 할 점

같은 LH 공고라도 CollectionRun이 다르면 새 수집 스냅샷으로 존재할 수 있다.

사용자 서비스에서는 모든 Announcement가 아니라 **active Collection에 포함된 Announcement**를 사용한다.

---

## 4.3 `backend/app/models/document.py`

### 역할

공고에 포함된 **HWP/HWPX 첨부문서 1개**를 저장한다.

주요 데이터:

```text
announcement_id
original_filename
document_format
storage_path
file_size_bytes
checksum_sha256
download_status
error_message
```

### 관계

```text
Announcement 1
    ↓
Document N
```

### 연동 시 알아야 할 점

- 문서 처리 기능의 기본 입력 키는 `document_id`다.
- `storage_path`는 실제 다운로드된 HWP/HWPX 파일 위치를 가리킨다.

---

## 4.4 `backend/app/models/processing_run.py`

### 역할

Document를 **한 번 처리한 실행 기록**으로 저장한다.

같은 Document를 재처리할 수 있기 때문에 Document와 분리되어 있다.

```text
Document 4
├─ ProcessingRun 10 : 성공
└─ ProcessingRun 11 : 재처리 실패
```

### 핵심 개념: `is_active`

서비스가 현재 신뢰하고 사용하는 처리 결과를 나타낸다.

```text
기존 정상 실행
is_active = true

새 실행
검증 전 / 실패
is_active = false
```

새 실행이 실패해도 기존 정상 데이터를 유지하기 위한 구조다.

### 정상 사용 조건

```text
execution_status = succeeded
verification_status = pass
is_active = true
```

---

## 4.5 `backend/app/models/processing_artifact.py`

### 역할

ProcessingRun에서 생성되는 **산출물 파일의 위치와 메타데이터를 추적**한다.

알고리즘을 저장하는 테이블이 아니라:

```text
어떤 실행에서
어떤 산출물이
어디에 생성되었는가
```

를 관리하는 DB 구조다.

---

## 4.6 `backend/app/models/document_structure.py`

### 역할

특정 ProcessingRun의 **구조화 문서 결과**를 저장한다.

```text
ProcessingRun
    ↓
DocumentStructure
```

### 연동 시 알아야 할 점

문서 처리 기능은 이 테이블에 직접 임의 INSERT하기보다 `pipeline_persistence.py`가 읽을 수 있는 산출물을 생성하는 것을 기본 연결 방식으로 사용한다.

---

## 4.7 `backend/app/models/chunk_set.py`

### 역할

특정 ProcessingRun에서 생성된 **Chunk 결과 한 묶음**을 버전 단위로 관리한다.

```text
ProcessingRun
    ↓
ChunkSet
    ↓
Chunk N
```

주요 데이터:

```text
chunker_version
strategy
chunking_config
status
is_active
chunk_count
```

### 연동 시 알아야 할 점

ChunkSet 자체가 Chunking 기준을 결정하는 것이 아니라, **특정 Chunking 실행 결과를 하나의 버전으로 묶어 관리**한다.

새 ChunkSet 검증이 끝나기 전까지 기존 active ChunkSet을 유지할 수 있다.

---

## 4.8 `backend/app/models/chunk.py`

### 역할

RAG 검색에서 사용하는 **실제 검색 단위**를 저장한다.

주요 데이터:

```text
content
embedding_text
section 정보
source 정보
metadata
announcement_id
chunk_set_id
```

### `announcement_id`를 직접 저장하는 이유

원래 관계는 다음과 같다.

```text
Chunk
→ ChunkSet
→ ProcessingRun
→ Document
→ Announcement
```

하지만 RAG에서는 선택된 공고 범위만 빠르게 검색해야 하므로 Chunk에 `announcement_id`를 직접 저장한다.

### 연동 시 알아야 할 점

RAG 검색은 반드시:

```text
active Collection
+
선택 Announcement
```

범위로 제한해야 한다.

---

## 4.9 `backend/app/models/embedding.py`

### 역할

Chunk의 **Vector 결과**를 저장한다.

```text
Chunk text
   ↓
Embedding model
   ↓
Embedding
```

주요 데이터:

```text
model_name
dimension
normalized
status
embedding vector
```

현재 검증된 기준:

```text
model = BAAI/bge-m3
dimension = 1024
```

### 연동 시 알아야 할 점

Collection publish 전에 모든 Chunk에 정상 Embedding이 존재해야 한다.

---

## 4.10 `backend/app/models/key_information.py`

### 역할

사용자 공고 상세 화면의 **핵심정보 카드 데이터**를 저장한다.

RAG 데이터와 목적이 다르다.

```text
KeyInformation
→ 핵심정보 카드

Chunk + Embedding
→ RAG 검색 / 답변
```

주요 영역:

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

### 연동 시 알아야 할 점

핵심정보 추출 결과는 테이블에 직접 INSERT하기보다:

```python
upsert_key_information(...)
```

을 사용한다.

---

## 4.11 `backend/app/models/error_log.py`

### 역할

Crawler / 문서 처리 / AI 처리 등에서 발생한 **운영 오류 기록**을 저장한다.

관리자 Error API가 이 데이터를 조회한다.

### 외부 기능에서 전달해야 할 최소 정보

```text
error_type
stage
message
관련 document / announcement
필요 시 error_code
```

---

## 4.12 `backend/app/models/system_state.py`

### 역할

사용자 서비스에서 현재 사용할 **active CollectionRun**을 관리한다.

핵심 값:

```text
active_collection_run_id
```

### 필요한 이유

```text
수집 완료
≠
서비스 준비 완료
```

새 Collection이 수집됐다고 바로 사용자에게 노출하지 않고, 문서 처리와 AI 결과까지 준비된 Collection만 publish하여 active로 전환한다.

---

# 5. Backend Service 코드 설명

---

## 5.1 `backend/app/services/collection_service.py`

### 한 줄 설명

**Crawler 반환값을 검증하고 `CollectionRun → Announcement → Document`로 DB에 저장하는 서비스**

### 주요 함수

```python
persist_collection_result(result)
collect_and_persist()
```

### `persist_collection_result(...)`

입력:

```text
Crawler가 반환한 dict
```

처리:

```text
반환 구조 검증
   ↓
CollectionRun INSERT
   ↓
Announcement INSERT
   ↓
HWP/HWPX Document INSERT
   ↓
생성 ID 반환
```

MVP 분석 대상 형식:

```text
hwp
hwpx
```

### `collect_and_persist()`

```text
Crawler 실행
   ↓
Crawler Result
   ↓
persist_collection_result(...)
```

Crawler 호출과 DB 저장을 연결한다.

### Crawler 기능에서 해야 할 일

`collection_service.py`를 수정하기보다 **정해진 반환 형식을 맞추는 것**이 기본 원칙이다.

필수 상위 구조:

```text
execution_id
execution_status
total_count
success_count
failed_count
fatal_error
data
```

---

## 5.2 `backend/app/services/pipeline_persistence.py`

### 한 줄 설명

**문서 처리 / AI Pipeline 산출물을 검증한 뒤 서비스 DB에 저장하는 핵심 Persistence 계층**

이 파일은 Parser / Chunking / Embedding 알고리즘을 실행하는 파일이 아니다.

```text
Pipeline outputs
   ↓
정합성 검증
   ↓
PostgreSQL 저장
```

### 읽는 대표 산출물

```text
step4-1_value_normalized.json
step4-3_verification.json
chunks.json
metadata.json
embeddings.npy
```

### 저장 대상

```text
ProcessingRun
DocumentStructure
ChunkSet
Chunk
Embedding
```

### 주요 검증

```text
Structure verification = pass
Structure filename / format 확인
Chunk 존재
Chunk ID 중복 여부
Embedding model 확인
Embedding dimension = 1024
normalized = true
Chunk 수 = Embedding 수
metadata와 Chunk ID 일치
NaN / Inf 방지
Vector normalization
```

### Activation

새 결과가 검증에 성공했을 때만 새 ProcessingRun / ChunkSet을 active로 전환한다.

### 다른 기능이 사용하는 방법

문서 처리와 AI / RAG 기능은 각각 자기 산출물을 생성한 뒤, **최종 산출물이 모두 준비된 시점에 `pipeline_persistence.py`의 저장 진입점을 통해 DB에 반영**한다.

각 기능에서 ORM 테이블에 직접 임의 INSERT하지 않는다.

---

## 5.3 `backend/app/services/key_information_service.py`

### 한 줄 설명

**핵심정보 추출 결과를 Announcement 단위로 INSERT / UPDATE하는 저장 서비스**

### 주요 함수

```python
upsert_key_information(...)
```

### 처리 흐름

```text
Announcement 존재 확인
   ↓
source_processing_run_id 검증
   ↓
기존 KeyInformation 조회
   ↓
없음 → INSERT
있음 → UPDATE
   ↓
추출 상태 / 검증 상태 저장
```

### 보호 로직

`source_processing_run_id`가 전달되면 해당 ProcessingRun이 실제로 같은 Announcement 소속인지 검증한다.

### 핵심정보 추출 기능에서 해야 할 일

```text
핵심정보 생성
   ↓
upsert_key_information(...)
```

을 호출한다.

DB 모델에 직접 INSERT하지 않는다.

---

## 5.4 `backend/app/services/collection_publish_service.py`

### 한 줄 설명

**새 Collection이 사용자 서비스에서 사용 가능한 상태인지 최종 검증하고 active Collection으로 전환하는 서비스**

### 주요 함수

```python
validate_collection_run_for_publish(collection_run_id)
publish_collection_run(collection_run_id)
```

### `validate_collection_run_for_publish(...)`

DB를 변경하지 않고 publish 가능 여부를 검사한다.

검증 조건:

```text
CollectionRun success
Announcement 존재
실패 공고 없음
Document 존재
Document download completed
active ProcessingRun 존재
ProcessingRun succeeded / verification pass
active ChunkSet completed
실제 Chunk 수 일치
모든 Chunk에 completed Embedding 존재
dimension = 1024
normalized = true
RAG Embedding model 일치
```

현재 검증 모델:

```text
BAAI/bge-m3
```

### `publish_collection_run(...)`

검증 통과 후:

```text
system_state.active_collection_run_id
```

를 해당 CollectionRun으로 변경한다.

이미 같은 Collection이 active면 중복 변경하지 않는다.

### 중요한 점

이 함수는:

```text
전체 Document 처리가 끝났다고 판단할 수 있는 주체
```

가 호출해야 한다.

수집 직후 Backend가 임의로 호출하면 안 된다.

---

## 5.5 `backend/app/services/pipeline_gateway.py`

### 한 줄 설명

**Backend API와 외부 실행 코드 사이의 경계를 만드는 callable Gateway**

Backend API에 Crawler / Parser / AI 실행 로직을 직접 넣지 않기 위해 사용한다.

### 주요 함수

```python
_load_callable(env_name)
collect_announcements()
recollect_announcement(announcement_id)
reprocess_document(document_id)
retry_error(error_id, document_id, stage)
```

### `_load_callable(...)`

환경변수에 다음 형식으로 등록된 함수를 import한다.

```text
module.path:function_name
```

사용하는 환경변수 계약:

```text
COLLECTION_RUNNER
ANNOUNCEMENT_RECOLLECTOR
DOCUMENT_REPROCESSOR
ERROR_RETRY_RUNNER
```

### 외부 기능이 제공할 callable 형태

#### 수집

```python
def collect():
    ...
```

#### 재수집

```python
def recollect(announcement_id: int):
    ...
```

#### 문서 재처리

```python
def reprocess(document_id: int):
    ...
```

#### 오류 재시도

```python
def retry(
    error_id,
    document_id,
    start_stage,
):
    ...
```

### 중요한 점

다른 기능 담당자가 Backend API 코드를 직접 수정하지 않고:

```text
자기 실행 함수 구현
   ↓
환경변수에 함수 경로 등록
   ↓
pipeline_gateway.py에서 호출
```

하도록 만든 경계다.

---

## 5.6 `backend/app/services/admin_service.py`

### 한 줄 설명

**관리자 화면에 필요한 DB 데이터를 조회하고 API Response 형태로 가공하는 Service**

주요 역할:

```text
공고 목록 / 상세 조회
문서 목록 / 상세 조회
ProcessingRun 조회
ErrorLog 조회
Error 상태 관리
```

예를 들어 관리자 공고 목록에서는:

```text
Announcement
+
CollectionRun 상태
+
KeyInformation 일부 값
```

등을 조합해 Response로 변환한다.

### Frontend에서 알아야 할 점

Frontend가 DB 구조를 직접 알 필요 없이 API Response만 사용하도록 중간 계층 역할을 한다.

---

# 6. API / Schema 코드 설명

## 6.1 `backend/app/api/routes/admin.py`

### 역할

HTTP Request를 받아 Service 또는 Gateway로 전달한다.

```text
Frontend Request
   ↓
FastAPI Route
   ↓
Service / Gateway
   ↓
Response Schema
```

DB 쿼리나 Pipeline 알고리즘을 Route에 직접 넣지 않는 것이 기본 원칙이다.

### 주요 API

```text
공고
GET    /api/admin/announcements
POST   /api/admin/announcements/collect
GET    /api/admin/announcements/{id}
POST   /api/admin/announcements/{id}/recollect

문서
GET    /api/admin/documents
GET    /api/admin/documents/{id}
GET    /api/admin/documents/{id}/download
POST   /api/admin/documents/{id}/reprocess

처리 상태
GET    /api/admin/processing-runs

오류
GET    /api/admin/errors
GET    /api/admin/errors/{id}
PATCH  /api/admin/errors/{id}/status
POST   /api/admin/errors/{id}/retry
```

---

## 6.2 `backend/app/schemas/admin.py`

### 역할

관리자 API의 **Request / Response 계약**이다.

Frontend 담당자가 가장 먼저 참고해야 하는 Backend 파일 중 하나다.

정의 대상:

```text
Announcement List / Detail
Document List / Detail
ProcessingRun
Structure 요약
Chunking 요약
Embedding 요약
Error List / Detail
Error status update request
```

### Frontend에서 알아야 할 점

화면에 필요한 값이 있다고 DB부터 수정하지 말고, 먼저 이 Schema와 기존 API Response를 확인한다.

API 계약 변경이 필요할 경우 Frontend / Backend가 이 파일을 기준으로 맞춘다.

---

# 7. 인증 / 세션

관리자 인증 흐름:

```text
POST /api/admin/auth/login
   ↓
인증 성공
   ↓
HttpOnly Cookie 발급
   ↓
GET /api/admin/auth/me
   ↓
세션 확인
   ↓
POST /api/admin/auth/logout
   ↓
Cookie 제거
```

AWS 실검증:

```text
LOGIN = 200
AUTH ME BEFORE LOGOUT = 200
LOGOUT = 200
AUTH ME AFTER LOGOUT = 401
SESSION MANAGEMENT = PASS
```

Frontend는 별도 sessionStorage 인증이 아니라 Backend 인증 API와 Cookie 계약을 사용해야 한다.

---

# 8. 기능별 실제 연결 방법

## 8.1 Crawler → Backend

```text
Crawler
   ↓ 결과 dict
collection_service.persist_collection_result(...)
   ↓
CollectionRun
Announcement
Document
```

Crawler 기능은 Backend DB 코드를 수정하기보다 **반환 구조를 맞추는 것**이 우선이다.

---

## 8.2 문서 처리 → Backend

문서 처리 담당 범위:

```text
HWP/HWPX Parsing
→ Normalizer
→ Structure
→ Verification
→ 핵심정보 추출
```

연결 흐름:

```text
Document ID
   ↓
문서 처리
   ↓
Structure / Verification 산출물
   ↓
pipeline_persistence.py에서 사용할 산출물
```

문서 처리 기능은 Chunking / Embedding / RAG 로직까지 직접 담당하지 않는다.

---

## 8.3 AI / RAG → Backend / DB

AI / RAG 담당 범위:

```text
Chunking
→ Embedding
→ Vector Search
→ Retrieval
→ Prompt
→ LLM Response
```

DB 연결:

```text
Chunk / Embedding 산출물
   ↓
pipeline_persistence.py
   ↓
Chunk / Embedding DB
```

RAG 검색:

```text
active Collection
+
선택 Announcement
   ↓
Vector Search
   ↓
RAG
```

---

## 8.4 핵심정보 추출 → Backend

```text
핵심정보 추출 결과
   ↓
upsert_key_information(...)
   ↓
KeyInformation
   ↓
GET /api/announcements/{id}
   ↓
사용자 핵심정보 카드
```

---

## 8.5 전체 처리 완료 → Publish

```text
모든 Document 처리 완료
   ↓
validate_collection_run_for_publish(...)
   ↓
통과
   ↓
publish_collection_run(...)
   ↓
SystemState.active_collection_run_id 변경
```

---

# 9. 구현 상태와 연동 상태

`완료`라는 표현이 혼동되지 않도록 아래처럼 구분한다.

- **구현 완료**: Backend 코드 자체가 준비됨
- **AWS 검증 완료**: 실제 AWS 환경에서 동작 확인
- **외부 연동 대기**: 상대 기능의 callable 또는 결과 연결 필요

| 파일 / 기능 | Backend 구현 | AWS 검증 | 외부 연동 상태 |
|---|---|---|---|
| `collection_service.py` | ✅ | ✅ | Crawler 결과 계약 유지 |
| `pipeline_persistence.py` | ✅ | ✅ 기존 정상 데이터 기준 | 문서 처리 / AI 산출물 연결 필요 |
| `key_information_service.py` | ✅ | 저장 로직 준비 | 핵심정보 추출 호출 필요 |
| `collection_publish_service.py` | ✅ | ✅ CollectionRun 5 validation | 호출 주체 / 시점 결정 필요 |
| `pipeline_gateway.py` | ✅ | Gateway 동작 확인 | Reprocess / Retry Runner 필요 |
| 관리자 인증 / 세션 | ✅ | ✅ | Frontend Cookie 연결 |
| 사용자 / 관리자 조회 API | ✅ | ✅ | Frontend 실제 화면 연결 |

---

# 10. 현재 AWS 실검증 상태

## Backend / DB

```text
GET /api/health
→ 200

GET /api/health/db
→ 200
```

## 사용자 API

```text
GET /api/announcements
→ 200

GET /api/announcements/2
→ 200
```

## 관리자 인증 / 세션

```text
LOGIN
→ 200

AUTH ME BEFORE LOGOUT
→ 200

LOGOUT
→ 200

AUTH ME AFTER LOGOUT
→ 401

SESSION MANAGEMENT
→ PASS
```

## 관리자 조회 API

```text
ANNOUNCEMENTS
→ 200

DOCUMENTS
→ 200

PROCESSING RUNS
→ 200

ERRORS
→ 200
```

검증 당시:

```text
Announcement       3건
Document           5건
ProcessingRun      7건
ErrorLog           0건
```

---

# 11. 실제 수집 상태

관리자 공고 수집 실행 결과:

```text
CollectionRun 6
status = success

Announcement 3

Document 4
Document 5
download_status = completed
```

현재 실제 자동 연결:

```text
관리자 공고 수집
   ↓
Crawler
   ↓
CollectionRun
   ↓
Announcement
   ↓
Document
```

신규 Document 4, 5에는 ProcessingRun이 없다.

따라서:

```text
Document
   ↓
문서 처리
   ↓
AI / RAG 처리
   ↓
Publish
```

구간은 아직 공통 통합 대상이다.

---

# 12. Publish 가능한 기존 정상 Collection

CollectionRun 5:

```text
Announcement        1
Document            2
Chunk               181
Embedding           181
Embedding model     BAAI/bge-m3
```

`validate_collection_run_for_publish(5)` 검증 통과.

현재:

```text
system_state.active_collection_run_id = 5
```

---

# 13. 다른 기능 담당자가 지켜야 할 연결 원칙

## Crawler

`collection_service.py`의 DB 저장 구조를 임의로 바꾸기보다 **반환 계약을 맞춘다.**

## 문서 처리

DB에 직접 임의 INSERT하지 않고 Structure / Verification 산출물을 생성한다.

## AI / RAG

Chunk / Embedding을 직접 테이블에 임의 INSERT하기보다 `pipeline_persistence.py`의 검증 / 저장 흐름을 사용한다.

## 핵심정보 추출

`key_information` 테이블에 직접 INSERT하지 않고:

```python
upsert_key_information(...)
```

을 사용한다.

## Frontend

DB 구조를 직접 사용하지 않고 API / Schema를 기준으로 연결한다.

---

# 14. 기능별 남은 작업

## Backend / DB

기능 구현과 AWS 검증은 완료 상태다.

남은 작업:

- 외부 기능에 Backend 계약 공유
- 통합 과정에서 API / DB 계약 지원
- 최종 PR 정리

---

## Crawler

- 수집 결과 계약 유지
- 재수집 callable 제공
- Pagination
- 다운로드 완료 처리
- 실패 정보 전달

---

## 문서 처리

- `document_id` 기반 실행 callable 제공
- HWP/HWPX Parsing
- Normalizer / Structure / Verification
- 핵심정보 추출
- 실패 stage / message 전달

---

## AI / RAG

- Chunk 생성
- BAAI/bge-m3 Embedding 생성
- Vector Search
- active Collection 기준 Retrieval
- Prompt / LLM Response
- 실패 정보 전달

---

## 핵심정보 추출 연동

- 추출 결과 생성
- `upsert_key_information(...)` 호출
- ProcessingRun 출처 연결
- 사용자 상세 API에서 실제 값 검증

---

## Frontend

- 관리자 Document 실제 API 연결
- 관리자 Error 실제 API 연결
- Error status PATCH 연결
- Recollect / Reprocess / Retry API 연결
- Backend Cookie 기반 세션 사용
- 실제 KeyInformation 표시 검증

---

# 15. 통합 단계에서 팀이 결정해야 할 항목

다음은 특정 기능 하나가 단독으로 결정하지 않는다.

1. **신규 Document 처리를 누가 시작하는가**
2. **모든 Document 처리가 완료됐음을 누가 판단하는가**
3. **`publish_collection_run()`을 누가 언제 호출하는가**
4. **Crawler / 문서 처리 / AI 오류를 ErrorLog에 어떤 방식으로 전달하는가**

---

# 16. 가장 중요한 연결 지점 요약

| 목적 | 사용할 Backend 코드 |
|---|---|
| Crawler 결과 저장 | `collection_service.py` |
| 문서 처리 / AI 산출물 저장 | `pipeline_persistence.py` |
| 핵심정보 저장 | `key_information_service.py` |
| 새 Collection 서비스 공개 | `collection_publish_service.py` |
| 외부 Runner 연결 | `pipeline_gateway.py` |
| 관리자 API | `admin.py` |
| Frontend API 계약 | `schemas/admin.py` |
| DB 구조 확인 | `models/*` |

각 기능 담당자는 자기 로직을 Backend 내부에 새로 넣는 것이 아니라, **정해진 연결 지점에 결과 또는 callable을 맞춰 연결**하면 된다.

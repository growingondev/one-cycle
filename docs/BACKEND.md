# Backend / DB 코드 가이드 및 기능별 인수인계

> 기준 시점: 2026-08-18
> 기준 브랜치: 최신 `develop` 통합 상태 + Backend 통합 보완 작업
> 목적: **Backend / DB에서 구현한 코드의 역할, 기능별 연결 지점, 현재 구현 상태와 남은 연동 항목을 정리한다.**
>
> 이 문서는 Git 작업 이력을 기록하는 문서가 아니라 **현재 최종 코드의 역할과 사용 방법을 설명하는 인수인계 문서**다.

---

# 1. Backend / DB 담당 범위

Backend / DB는 다음을 담당한다.

```text
API 서버
DB 모델
DB 조회 / 저장
Persistence
관리자 인증 / 세션 관리
Collection 관리
ErrorLog 관리
외부 기능 호출 Gateway
기능 사이 입력 / 출력 계약
서비스용 active 데이터 관리
```

Crawler, Parser, Chunking, Embedding, RAG 등의 내부 알고리즘은 Backend에서 직접 구현하지 않는다.

전체적인 역할은 다음과 같다.

```text
Crawler / 문서 처리 / AI 기능
            ↓
      Backend Service
            ↓
       데이터 검증
            ↓
       PostgreSQL
            ↓
      Backend API
            ↓
Frontend / RAG / 관리자
```

---

# 2. 기능 영역 경계

통합 과정에서 각 기능의 책임이 섞이지 않도록 아래 기준을 사용한다.

## Backend / DB

```text
FastAPI
DB Model
DB Persistence
DB 조회
관리자 인증 / 세션
Collection 상태 관리
ErrorLog 저장 / 조회
외부 기능 호출 Gateway
사용자 / 관리자 API
```

## Crawler

```text
LH 공고 수집
상세 페이지 접근
첨부파일 다운로드
Pagination
Selenium 처리
실제 문서 형식 판별
다운로드 결과 생성
수집 실패 정보 생성
```

## 문서 처리

```text
HWP / HWPX Parsing
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
관리자 Session Cookie 사용
```

---

# 3. 전체 데이터 흐름

```text
LH 청약플러스
    ↓
Crawler
    ↓
Collection Result
    ↓
collection_service.py
    ↓
CollectionRun
    ↓
Announcement
    ↓
Document
    ↓
문서 처리 Pipeline
    ↓
ProcessingRun
    ↓
DocumentStructure
    ↓
ChunkSet
    ↓
Chunk
    ↓
Embedding
    ↓
Collection Publish 검증
    ↓
SystemState.active_collection_run_id
    ↓
사용자 서비스 / RAG
```

핵심정보 카드는 별도 흐름으로 저장한다.

```text
Document 처리 결과
    ↓
핵심정보 추출
    ↓
key_information_service.py
    ↓
KeyInformation
    ↓
공고 상세 핵심정보 카드
```

오류는 별도로 기록한다.

```text
Crawler / 문서 처리 / AI 기능 오류
    ↓
error_log_service.py
    ↓
ErrorLog
    ↓
관리자 오류 관리 API
```

---

# 4. 기능별 우선 확인 Backend 파일

| 기능 영역 | 우선 확인할 파일 | 확인 목적 |
|---|---|---|
| Crawler | `collection_service.py` → `collection_run.py` → `announcement.py` → `document.py` → `pipeline_gateway.py` | Crawler 결과를 어떤 형식으로 전달하고 DB에 어떻게 저장하는지 확인 |
| 문서 처리 | `document.py` → `processing_run.py` → `document_structure.py` → `pipeline_persistence.py` → `pipeline_gateway.py` | `document_id` 기반 처리와 Structure / Verification 결과 연결 방식 확인 |
| AI / RAG | `chunk_set.py` → `chunk.py` → `embedding.py` → `system_state.py` → `pipeline_persistence.py` → `collection_publish_service.py` | Chunk / Embedding 저장과 active 데이터 기준 확인 |
| 핵심정보 추출 | `key_information.py` → `key_information_service.py` | 핵심정보 저장 필드와 upsert 계약 확인 |
| 오류 기록 | `error_log.py` → `error_log_service.py` | 오류 저장 형식과 관련 ID 연결 방식 확인 |
| Frontend | `backend/app/api/routes/` → `backend/app/schemas/` | API Endpoint와 Request / Response 계약 확인 |

---

# 5. DB 구조

주요 관계는 다음과 같다.

```text
CollectionRun
    ↓
Announcement
    ↓
Document
    ↓
ProcessingRun
    ├──────────────→ DocumentStructure
    ├──────────────→ ProcessingArtifact
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
Collection / Announcement / Document / ProcessingRun과 선택적 연결
```

---

# 6. DB Model 설명

## 6.1 `collection_run.py`

### 역할

공고 수집 **1회 실행 전체를 하나의 단위로 기록**한다.

```text
관리자 공고 수집 1회
→ CollectionRun 1개
```

대표 상태:

```text
running
success
partial
failed
```

주요 데이터:

```text
execution_id
status
total_announcement_count
successful_announcement_count
failed_announcement_count
fatal_error
finished_at
```

### 연동 기준

- Crawler 결과 저장 시 가장 먼저 생성된다.
- Collection publish도 `collection_run_id` 기준으로 수행한다.
- 사용자 서비스는 모든 Collection이 아니라 active Collection을 사용한다.

---

## 6.2 `announcement.py`

### 역할

LH 공고 1건을 저장한다.

주요 데이터:

```text
source_announcement_id
title
detail_url
region
announcement_date
publication_status
collection_run_id
```

관계:

```text
CollectionRun 1
    ↓
Announcement N
```

같은 LH 공고라도 CollectionRun이 다르면 서로 다른 수집 스냅샷으로 존재할 수 있다.

---

## 6.3 `document.py`

### 역할

공고에 포함된 HWP / HWPX 첨부문서 1개를 저장한다.

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

관계:

```text
Announcement 1
    ↓
Document N
```

### 중요

문서 처리 Pipeline의 기본 입력 키는:

```text
document_id
```

이다.

`storage_path`는 실제 다운로드된 문서 파일의 위치를 가리킨다.

---

## 6.4 `processing_run.py`

### 역할

Document를 **한 번 처리한 실행 기록**으로 저장한다.

같은 문서를 다시 처리할 수 있으므로 Document와 ProcessingRun을 분리한다.

```text
Document
├─ ProcessingRun A
└─ ProcessingRun B
```

주요 상태:

```text
execution_status
verification_status
current_stage
error_stage
error_code
error_message
```

### active 개념

서비스에서 현재 신뢰하는 처리 결과만:

```text
is_active = true
```

로 설정한다.

정상 active 조건:

```text
execution_status = succeeded
verification_status = pass
activated_at != null
```

새 처리가 실패해도 기존 정상 ProcessingRun을 유지할 수 있도록 설계되어 있다.

---

## 6.5 `processing_artifact.py`

### 역할

ProcessingRun에서 생성된 산출물의 위치와 메타데이터를 관리한다.

```text
어떤 ProcessingRun에서
어떤 산출물이 생성됐고
어디에 저장되어 있는가
```

를 기록한다.

---

## 6.6 `document_structure.py`

### 역할

특정 ProcessingRun의 구조화 결과를 저장한다.

```text
ProcessingRun
    ↓
DocumentStructure
```

Parser / Normalizer / Structure 내부 알고리즘 자체를 저장하는 것이 아니라, 최종 구조화 결과를 DB에 연결한다.

---

## 6.7 `chunk_set.py`

### 역할

특정 ProcessingRun에서 생성된 Chunk 결과 한 묶음을 관리한다.

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

### 중요

ChunkSet 자체가 Chunk 기준을 결정하는 것이 아니다.

```text
특정 Chunking 실행 결과
→ 하나의 ChunkSet 버전으로 저장
```

하는 구조다.

새 ChunkSet이 검증되기 전에는 기존 active ChunkSet을 유지할 수 있다.

---

## 6.8 `chunk.py`

### 역할

RAG 검색에서 사용하는 실제 검색 단위를 저장한다.

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

원래 관계는:

```text
Chunk
→ ChunkSet
→ ProcessingRun
→ Document
→ Announcement
```

이지만, RAG 검색 시 공고 범위를 빠르게 제한하기 위해 Chunk에도 `announcement_id`를 저장한다.

RAG 검색 범위는 반드시:

```text
active Collection
+
선택 Announcement
```

범위로 제한한다.

---

## 6.9 `embedding.py`

### 역할

Chunk의 Embedding Vector를 저장한다.

```text
Chunk
    ↓
Embedding Model
    ↓
Embedding
```

현재 Backend publish 검증 기준:

```text
model = BAAI/bge-m3
dimension = 1024
normalized = true
status = completed
```

모든 Chunk에 정상 Embedding이 존재해야 Collection publish가 가능하다.

---

## 6.10 `key_information.py`

### 역할

사용자 공고 상세 화면에서 표시할 핵심정보 데이터를 저장한다.

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

핵심정보 추출 결과는 직접 INSERT하기보다 Backend Service를 사용한다.

```python
upsert_key_information(...)
```

---

## 6.11 `error_log.py`

### 역할

Crawler / 문서 처리 / AI / Backend 처리 과정에서 발생한 운영 오류를 저장한다.

관리자 Error API가 이 데이터를 조회한다.

지원하는 오류 유형:

```text
collection
download
parsing
normalizing
structuring
verification
chunking
embedding
database
rag
llm
```

상태:

```text
unresolved
in_progress
resolved
```

주요 데이터:

```text
collection_run_id
announcement_id
document_id
processing_run_id

error_type
error_code
stage
message
stack_trace

status
resolution
created_at
resolved_at
```

---

## 6.12 `system_state.py`

### 역할

현재 사용자 서비스에서 사용할 active Collection을 관리한다.

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

새 공고가 수집됐다고 바로 사용자에게 노출하지 않는다.

다음 결과가 모두 준비되고 검증된 Collection만 publish한다.

```text
Document 처리
Structure 검증
Chunk 생성
Embedding 생성
```

---

# 7. Backend Service 설명

## 7.1 `collection_service.py`

### 역할

Crawler 반환 결과를 검증하고 다음 구조로 저장한다.

```text
Crawler Result
    ↓
CollectionRun
    ↓
Announcement
    ↓
Document
```

주요 함수:

```python
persist_collection_result(result)
collect_and_persist()
```

### `persist_collection_result(...)`

Crawler가 반환한 dict를 DB에 저장한다.

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

Crawler의 `data`는 공고 목록이다.

각 공고에는 최소한 다음 정보가 필요하다.

```text
source_announcement_id
title
detail_url
region
post_date
publication_status
documents
```

---

### Document 계약

Crawler에서 전달되는 Document의 주요 값:

```text
file_name
file_format
storage_path
file_size_bytes
checksum_sha256
download_status
error_message
```

Backend MVP 분석 대상 형식:

```text
hwp
hwpx
```

다른 형식은 분석 대상 Document로 저장하지 않는다.

---

### `file_format` 기준

`file_format`은 **파일명 확장자가 아니라 다운로드가 완료된 실제 파일 내부 형식**을 기준으로 한다.

정상 형식:

```text
hwp
hwpx
```

판별 불가:

```text
unknown
```

Crawler는 다운로드된 실제 파일에 대해 형식을 판별한다.

Backend는 다음만 저장한다.

```text
hwp
hwpx
```

`unknown`은 분석 대상 Document 저장에서 제외한다.

---

### 다운로드 완료 기준

Crawler는 Document를 Backend에 전달하기 전에 다운로드를 완료하고 다음 정보를 확정한다.

```text
file_name
file_format
storage_path
file_size_bytes
checksum_sha256
download_status
```

다운로드 지연 상태의 임시 파일을 먼저 Backend로 전달하지 않는다.

---

### `collect_and_persist()`

```text
Crawler 실행
    ↓
Crawler Result
    ↓
persist_collection_result(...)
    ↓
CollectionRun / Announcement / Document 저장
```

Crawler 호출과 DB 저장을 연결하는 Backend callable이다.

---

## 7.2 `pipeline_persistence.py`

### 역할

문서 처리 / AI Pipeline 산출물을 검증한 뒤 서비스 DB에 저장한다.

이 파일은:

```text
Parser 실행기
Chunking 실행기
Embedding 실행기
```

가 아니다.

역할은:

```text
Pipeline outputs
    ↓
정합성 검증
    ↓
DB 저장
```

이다.

대표 저장 대상:

```text
ProcessingRun
DocumentStructure
ChunkSet
Chunk
Embedding
```

대표 검증:

```text
Structure verification = pass
Structure filename 확인
Structure format 확인
Chunk 존재 여부
Chunk ID 중복 확인
Embedding model 확인
Embedding dimension 확인
normalized 확인
Chunk 수와 Embedding 수 일치 확인
Embedding metadata와 Chunk ID 확인
NaN / Inf 방지
Vector normalization 확인
```

### filename / format 검증

Backend는 Pipeline 결과의:

```text
filename
format
```

을 DB의:

```text
Document.original_filename
Document.document_format
```

과 비교한다.

불일치하면 저장을 거부한다.

Backend 쪽 검증을 느슨하게 변경하지 않는다.

문서 처리 Pipeline에서 원본 filename / 실제 format을 일관되게 전달해야 한다.

---

## 7.3 `key_information_service.py`

### 역할

핵심정보 추출 결과를 Announcement 기준으로 저장 / 갱신한다.

주요 함수:

```python
upsert_key_information(...)
```

검증 항목:

```text
Announcement 존재 여부
ProcessingRun 존재 여부
ProcessingRun과 Document / Announcement 관계
추출 상태
검증 상태
```

Announcement당 핵심정보 레코드를 하나의 최신 상태로 관리한다.

핵심정보를 실제로 추출하는 알고리즘은 문서 처리 기능에서 담당한다.

---

## 7.4 `collection_publish_service.py`

### 역할

새 Collection이 실제 사용자 서비스에서 사용할 수 있는 상태인지 검증한 뒤 active Collection으로 전환한다.

대표 함수:

```python
validate_collection_run_for_publish(...)
publish_collection_run(...)
```

검증 기준:

```text
CollectionRun 상태 정상
Document 처리 완료
active ProcessingRun 존재
ProcessingRun succeeded
verification pass
active ChunkSet 존재
Chunk 존재
Embedding 완료
Chunk 수 = Embedding 수
Embedding model 일치
dimension = 1024
normalized = true
```

검증을 통과한 경우:

```text
SystemState.active_collection_run_id
```

를 새 CollectionRun으로 변경한다.

### 중요

수집 직후 Backend가 임의로 publish하지 않는다.

```text
전체 Document 처리가 끝났다고 판단할 수 있는 실행 주체
```

가 최종 publish 시점에 호출해야 한다.

---

## 7.5 `error_log_service.py`

### 역할

다른 기능에서 발생한 오류를 공통 ErrorLog 형식으로 저장한다.

외부 기능에서 `error_logs` 테이블에 직접 INSERT하지 않고 다음 함수를 사용하는 것을 권장한다.

```python
from backend.app.services.error_log_service import record_error
```

주요 함수:

```python
record_error(...)
```

최소 입력:

```text
error_type
stage
message
```

필요에 따라 다음 ID를 함께 전달한다.

```text
collection_run_id
announcement_id
document_id
processing_run_id
```

추가 정보:

```text
error_code
stack_trace
```

### 관계 보완

일부 하위 ID만 전달되어도 DB 관계를 따라 가능한 상위 ID를 확인한다.

```text
ProcessingRun
    ↓
Document
    ↓
Announcement
    ↓
CollectionRun
```

예를 들어:

```text
processing_run_id만 전달
```

된 경우 관련:

```text
document_id
announcement_id
collection_run_id
```

을 DB 관계를 통해 확인한다.

관계가 서로 일치하지 않으면 오류 저장을 거부한다.

---

## 7.6 `pipeline_gateway.py`

### 역할

Backend API와 외부 실행 코드 사이의 경계를 만든다.

Backend API 내부에:

```text
Crawler 실행 코드
Parser 실행 코드
AI 실행 코드
```

를 직접 작성하지 않고 callable을 통해 연결한다.

주요 함수:

```python
_load_callable(env_name)
collect_announcements()
recollect_announcement(announcement_id)
reprocess_document(document_id)
retry_error(error_id, document_id, stage)
```

환경변수에는 다음 형식의 callable을 지정한다.

```text
module.path:function_name
```

사용 환경변수:

```text
COLLECTION_RUNNER
ANNOUNCEMENT_RECOLLECTOR
DOCUMENT_REPROCESSOR
ERROR_RETRY_RUNNER
```

---

### 현재 연결 완료

수집 Runner는 현재 구현과 호출 계약이 확인되어 있다.

```env
COLLECTION_RUNNER=backend.app.services.collection_service:collect_and_persist
```

흐름:

```text
관리자 수집 API
    ↓
pipeline_gateway
    ↓
collect_and_persist()
    ↓
Crawler
    ↓
Crawler Result
    ↓
DB Persistence
```

---

### 현재 외부 callable 연결 대기

```text
ANNOUNCEMENT_RECOLLECTOR
DOCUMENT_REPROCESSOR
ERROR_RETRY_RUNNER
```

위 세 기능은 실제 실행 callable이 구현 / 확정된 뒤 연결한다.

존재하지 않는 함수 경로를 임의로 `.env`에 등록하지 않는다.

---

## 7.7 `admin_service.py`

### 역할

관리자 화면에 필요한 DB 데이터를 조회하고 API Response 형태로 가공한다.

주요 기능:

```text
공고 목록 / 상세 조회
문서 목록 / 상세 조회
ProcessingRun 조회
ErrorLog 조회
Error 상태 변경
```

Frontend는 DB 구조를 직접 알 필요 없이 Backend API Response만 사용한다.

---

## 7.8 `chat_service.py`

### 역할

Backend Chat API와 RAG callable 사이를 연결한다.

환경변수:

```env
RAG_ANSWER_FUNCTION=rag.service:answer_question
```

RAG 함수 계약:

```python
answer_question(
    announcement_id: int,
    question: str,
) -> dict
```

대표 결과:

```json
{
  "answer": "답변",
  "grounded": true,
  "evidence": [
    {
      "chunkId": "chunk id",
      "sectionTitle": "섹션",
      "content": "근거",
      "score": 0.9
    }
  ]
}
```

Backend는 이 결과를 `ChatResponse`로 검증해 API로 반환한다.

---

# 8. Backend API

## 8.1 Health

```text
GET /api/health
GET /api/health/db
```

---

## 8.2 사용자 공고 API

```text
GET /api/announcements
GET /api/announcements/{announcement_id}
```

사용자 공고 조회는 active Collection 기준으로 제공한다.

---

## 8.3 Chat

```text
POST /api/chat
```

입력:

```json
{
  "announcementId": 1,
  "question": "신청 자격이 뭐야?"
}
```

---

## 8.4 관리자 인증 / Session

```text
POST /api/admin/auth/login
POST /api/admin/auth/logout
GET  /api/admin/auth/me
```

인증 방식은 관리자 Session Cookie 기반이다.

동작 기준:

```text
Login
→ Session Cookie 발급

/api/admin/auth/me
→ 로그인 상태 확인

Logout
→ Session 종료

Logout 후 /me
→ 401
```

---

## 8.5 관리자 공고 API

```text
GET  /api/admin/announcements
GET  /api/admin/announcements/{announcement_id}
POST /api/admin/announcements/collect
POST /api/admin/announcements/{announcement_id}/recollect
```

---

## 8.6 관리자 문서 API

```text
GET  /api/admin/documents
GET  /api/admin/documents/{document_id}
GET  /api/admin/documents/{document_id}/download
POST /api/admin/documents/{document_id}/reprocess
```

---

## 8.7 ProcessingRun API

```text
GET /api/admin/processing-runs
```

---

## 8.8 Error API

```text
GET   /api/admin/errors
GET   /api/admin/errors/{error_id}
POST  /api/admin/errors/{error_id}/retry
PATCH /api/admin/errors/{error_id}/status
```

Backend에는 다음 API가 존재하지 않는다.

```text
/api/admin/errors/export
/api/admin/errors/{id}/notes
```

Frontend 연동 시 실제 Backend API 계약을 기준으로 구현해야 한다.

---

# 9. 환경변수

`.env.example`을 기준으로 사용한다.

실제 `.env`는 Git에 commit하지 않는다.

---

## PostgreSQL

```env
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=one_cycle
POSTGRES_USER=one_cycle
POSTGRES_PASSWORD=CHANGE_ME
```

---

## Embedding

```env
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_USE_FP16=true
EMBEDDING_REQUIRE_CUDA=true
EMBEDDING_DEVICE_INDEX=0
```

---

## LLM

```env
LLAMA_BASE_URL=http://127.0.0.1:8080
LLAMA_MODEL=qwen2.5-7b-instruct
LLAMA_TIMEOUT_SECONDS=600
```

---

## RAG

```env
RAG_ANSWER_FUNCTION=rag.service:answer_question
RAG_DB_TOP_K=5
```

MVP 관련 설정:

```env
MVP_ANNOUNCEMENT_ID=1
MVP_DOCUMENT_FORMAT=hwpx
```

---

## 관리자 인증

```env
ADMIN_ID=admin
ADMIN_PASSWORD=CHANGE_ME
ADMIN_JWT_SECRET=CHANGE_ME
```

Session / Cookie:

```env
ADMIN_JWT_EXPIRE_SECONDS=3600
ADMIN_COOKIE_NAME=admin_access_token
ADMIN_COOKIE_SECURE=false
ADMIN_COOKIE_SAMESITE=lax
```

---

## Backend Pipeline Gateway

현재 연결 완료:

```env
COLLECTION_RUNNER=backend.app.services.collection_service:collect_and_persist
```

외부 callable 연결 대기:

```env
# ANNOUNCEMENT_RECOLLECTOR=
# DOCUMENT_REPROCESSOR=
# ERROR_RETRY_RUNNER=
```

---

# 10. Collection Publish 기준

수집 성공만으로 사용자 서비스에 바로 노출하지 않는다.

```text
Collection 수집
    ↓
Document 저장
    ↓
문서 처리
    ↓
Structure 검증
    ↓
Chunking
    ↓
Embedding
    ↓
Collection Publish Validation
    ↓
active Collection 전환
```

대표 검증 흐름:

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

# 11. active 데이터 기준

## Collection

```text
SystemState.active_collection_run_id
```

에 등록된 Collection만 사용자 서비스 대상으로 사용한다.

---

## ProcessingRun

정상 서비스 데이터:

```text
execution_status = succeeded
verification_status = pass
is_active = true
```

---

## ChunkSet

서비스 검색에 사용할 ChunkSet:

```text
status = completed
is_active = true
```

---

## Embedding

```text
status = completed
model_name = BAAI/bge-m3
dimension = 1024
normalized = true
```

---

# 12. 기능 간 Integration Contract

## 12.1 Crawler → Backend

Crawler 결과:

```text
execution_id
execution_status
total_count
success_count
failed_count
fatal_error
data
```

Document:

```text
file_name
file_format
storage_path
file_size_bytes
checksum_sha256
download_status
error_message
```

`file_format`:

```text
실제 내부 형식 기준

hwp
hwpx
unknown
```

Backend는:

```text
hwp
hwpx
```

만 분석 대상 Document로 저장한다.

---

## 12.2 문서 처리 → Backend

기본 식별자:

```text
document_id
```

Backend Persistence는 다음을 검증한다.

```text
DB Document
↔
Pipeline 결과
```

특히:

```text
original_filename
document_format
```

이 일치해야 한다.

Parser 실행 과정에서 내부 형식에 맞는 임시 alias 파일을 사용하더라도, 최종 Structure 결과에는 DB의 원본 filename 정보가 유지되어야 한다.

Backend 검증을 우회하기 위해 filename 검증을 느슨하게 변경하지 않는다.

---

## 12.3 핵심정보 추출 → Backend

추출 결과:

```text
application_period
eligibility
supply_information
income_asset_criteria
required_documents
winner_announcement
contact_information
```

저장은:

```python
upsert_key_information(...)
```

을 사용한다.

---

## 12.4 Chunking / Embedding → Backend

Chunk:

```text
document_id
announcement_id
chunk_id
order
type
section
content
embedding_text
source metadata
```

Embedding:

```text
chunk_id
model
dimension
normalized
status
vector
```

최종 Persistence에서 Chunk / Embedding 개수와 ID 정합성을 검증한다.

---

## 12.5 RAG → Backend

Backend가 호출하는 함수:

```python
answer_question(
    announcement_id: int,
    question: str,
) -> dict
```

RAG는 다음 범위로 검색해야 한다.

```text
active Collection
+
선택 Announcement
+
active ProcessingRun
+
active ChunkSet
+
정상 Embedding
```

---

## 12.6 오류 발생 기능 → Backend

오류를 DB에 직접 INSERT하지 않고:

```python
record_error(...)
```

사용을 권장한다.

예:

```python
record_error(
    error_type="parsing",
    stage="parsing",
    message="문서 파싱 실패",
    document_id=document_id,
    processing_run_id=processing_run_id,
)
```

---

# 13. 구현 / 연동 상태

`완료` 표현이 혼동되지 않도록 다음으로 구분한다.

```text
구현 완료
→ Backend 코드 자체 준비

AWS 검증
→ 실제 AWS 환경 동작 확인

외부 연동 대기
→ 다른 기능의 callable 또는 결과 연결 필요
```

| 파일 / 기능 | Backend 구현 | 검증 상태 | 외부 연동 상태 |
|---|---|---|---|
| `collection_service.py` | ✅ | AWS 동작 확인 | Crawler 결과 계약 연결 완료 |
| `pipeline_persistence.py` | ✅ | 기존 정상 데이터 기준 AWS 확인 | 문서 처리 / AI 산출물에서 호출 연결 필요 |
| `key_information_service.py` | ✅ | 저장 로직 준비 | 핵심정보 추출 기능에서 호출 필요 |
| `collection_publish_service.py` | ✅ | 실제 Collection validation 확인 | 최종 자동 호출 주체 / 시점 결정 필요 |
| `error_log_service.py` | ✅ | Backend Contract Test 통과 | 각 기능 오류 발생 지점에서 호출 필요 |
| `pipeline_gateway.py` | ✅ | Gateway / Collection Runner 확인 | Recollect / Reprocess / Retry Runner 필요 |
| 관리자 인증 / Session | ✅ | AWS 확인 | Frontend 실제 Cookie 연결 필요 |
| 사용자 / 관리자 조회 API | ✅ | AWS 확인 | Frontend 실제 화면 연결 필요 |
| Chat Gateway | ✅ | RAG callable 계약 확인 | RAG 서비스와 연동 |
| Backend Contract Test | ✅ | 15개 테스트 PASS | 지속 유지 |

---

# 14. 현재 확인된 Backend Contract Test

실행 명령:

```bash
python -m unittest discover -s tests/backend -p "test_*.py" -v
```

현재 테스트 대상:

```text
Crawler Collection Result 기본 구조
execution_id 필수
Collection status 검증
data list 검증

Document format 계약
hwp / hwpx 허용
unknown 제외

Pipeline Gateway 환경변수 검증
설정된 callable 호출 검증

RAG 결과 → ChatResponse 변환
잘못된 RAG 결과 거부

ErrorLog error_type 검증
ErrorLog stage 검증
ErrorLog message 검증
ProcessingRun → Document → Announcement → CollectionRun 관계 보완
관련 ID 불일치 거부
```

현재 결과:

```text
15 tests
PASS
```

---

# 15. AWS에서 확인된 Backend 범위

## Health

```text
GET /api/health
→ 200

GET /api/health/db
→ 200
```

---

## 사용자 API

```text
GET /api/announcements
→ 정상 응답

GET /api/announcements/{id}
→ 정상 응답
```

---

## 관리자 인증

```text
Login
→ 200

Auth Me
→ 200

Logout
→ 200

Logout 이후 Auth Me
→ 401
```

즉 Session lifecycle:

```text
Login
→ 인증 상태
→ Logout
→ 인증 해제
```

가 정상 동작하는 것을 확인했다.

---

## 관리자 API

다음 범위의 정상 응답을 확인했다.

```text
공고 목록
문서 목록
ProcessingRun 목록
Error 목록
```

---

## Collection / DB

실제 Collection 데이터를 대상으로:

```text
Collection
Document
ProcessingRun
ChunkSet
Chunk
Embedding
```

저장 구조를 확인했다.

Collection publish validation도 실제 저장 데이터를 대상으로 확인했다.

---

# 16. 현재 남은 Integration 항목

Backend 핵심 기능 자체보다 **기능 간 연결 작업**이 남아 있다.

## Crawler

현재 실제 문서 내부 형식 판별과 다운로드 지연 처리 문제는 Crawler 코드에서 보완되었다.

Backend에서는 별도 Crawler 알고리즘 수정이 필요하지 않다.

---

## 문서 처리

확인할 항목:

```text
Pipeline 실행 완료 후 Backend Persistence 호출
Structure filename 원본 유지
Structure format 실제 형식 유지
핵심정보 추출 결과 → key_information_service 연결
```

---

## AI / RAG

확인할 항목:

```text
Pipeline 완료 후 Persistence 연결
Collection publish 호출 시점
RAG active Collection 범위 유지
```

---

## ErrorLog

현재 Backend 공통 저장 함수는 준비되어 있다.

남은 작업:

```text
Crawler 오류 발생
→ record_error(...)

문서 처리 오류 발생
→ record_error(...)

Embedding 오류 발생
→ record_error(...)

RAG / LLM 오류 발생
→ record_error(...)
```

각 기능이 실제 오류 발생 지점에서 호출하도록 연결해야 한다.

---

## Gateway

현재:

```text
COLLECTION_RUNNER
```

는 연결 가능하다.

남은 항목:

```text
ANNOUNCEMENT_RECOLLECTOR
DOCUMENT_REPROCESSOR
ERROR_RETRY_RUNNER
```

각 실제 실행 callable이 확정되면 `.env`에 연결한다.

---

## Frontend

관리자 Frontend는 Backend의 실제 API Endpoint를 기준으로 연결해야 한다.

특히 확인할 계약:

```text
공고:
GET /api/admin/announcements

수집:
POST /api/admin/announcements/collect

문서:
GET /api/admin/documents

오류:
GET /api/admin/errors

오류 상태:
PATCH /api/admin/errors/{error_id}/status
```

관리자 Login도 mock session이 아니라 Backend Session Cookie를 사용해야 한다.

---

# 17. 작업 시 주의사항

## DB

PostgreSQL 데이터는 Docker Volume에 저장된다.

```text
Container 삭제
≠
Volume 삭제
```

DB 데이터를 유지해야 하는 환경에서는 Volume을 임의로 삭제하지 않는다.

---

## Migration

DB Schema 변경 시 직접 운영 DB를 수정하기보다 Alembic Migration을 사용한다.

```text
Model 수정
    ↓
Migration
    ↓
DB 적용
```

---

## Pipeline

다른 기능의 내부 알고리즘을 Backend 코드에서 복제하지 않는다.

```text
잘못된 방식

Backend Route
→ Parser 로직 직접 작성
→ Chunking 직접 작성
→ Embedding 직접 작성
```

대신:

```text
Backend Route
→ Gateway / Service
→ 외부 기능 callable
```

형태로 연결한다.

---

## Persistence

외부 기능이 DB 테이블에 임의로 직접 INSERT하기보다 Backend Persistence Service를 통해 저장하도록 한다.

이 방식으로:

```text
Validation
관계 검증
active 상태
버전 관리
```

를 일관되게 유지한다.

---

# 18. Backend 작업 완료 기준

Backend 기능은 단순히 파일이 존재한다고 완료로 보지 않는다.

다음 조건을 기준으로 한다.

```text
코드 구현
    ↓
입력 / 출력 계약 확인
    ↓
DB 관계 검증
    ↓
Contract Test
    ↓
API 동작 확인
    ↓
Integration 연결
```

---

# 19. 현재 Backend 요약

현재 Backend / DB 범위에서 구현된 주요 기능:

```text
PostgreSQL + pgvector Schema

CollectionRun
Announcement
Document
ProcessingRun
DocumentStructure
ProcessingArtifact
ChunkSet
Chunk
Embedding
KeyInformation
ErrorLog
SystemState

Crawler Result Persistence
Pipeline Result Persistence
KeyInformation Persistence
Collection Publish Validation
ErrorLog Persistence

사용자 API
관리자 API
관리자 인증 / Session
RAG Chat Gateway
Pipeline Gateway

Backend Contract Test
```

현재 단계는:

```text
Backend 핵심 구현
→ 완료

Backend / DB AWS 검증
→ 주요 범위 완료

기능별 알고리즘 구현
→ 각 기능 영역 담당

남은 Backend 작업
→ 기능 간 연결 확인
→ Integration 지원
→ Contract Test 유지
→ 최종 AWS Smoke Test
```

이다.

---

# 20. 최종 원칙

Backend / DB의 역할은 다른 기능의 알고리즘을 대신 구현하는 것이 아니다.

```text
Crawler
문서 처리
AI / RAG
Frontend
```

가 각 기능을 구현하고,

Backend는:

```text
입력 계약
    ↓
검증
    ↓
DB 저장
    ↓
상태 관리
    ↓
API 제공
```

을 책임진다.

기능 간 연결에서 문제가 발생하면 먼저:

```text
입력값
파일명
문서 형식
ID 관계
상태값
active 여부
환경변수 callable
```

계약이 일치하는지 확인한다.

Backend 검증을 임의로 느슨하게 만들기보다, 각 기능의 출력이 정해진 계약을 맞추도록 수정하는 것을 기본 원칙으로 한다.
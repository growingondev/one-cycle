# Backend Integration

> 목적: 최신 Crawler / 문서 처리 / AI 기능과 Backend API / DB 사이의 연결 계약을 정리하고, 이번 Backend 통합 작업에서 완료한 항목과 남은 항목을 기록한다.
>
> 이 문서는 Backend 전체 코드 설명서가 아니라 `feature/backend-integration`에서 진행한 통합 작업만 다룬다.

---

# 1. 작업 목적

기존 Backend / DB 기능은 API, DB Model, Persistence, 인증 / 세션, Gateway를 중심으로 구현되어 있었다.

이번 작업의 목적은 각 기능 담당자의 최신 코드가 `develop`에 반영되는 과정에서 Backend와 실제로 연결 가능한지 확인하고, 부족한 Backend 계약을 보완하는 것이다.

전체 연결 구조는 다음과 같다.

```text
Crawler / Document Processing / AI
                ↓
        Backend Gateway
                ↓
       Backend Persistence
                ↓
          PostgreSQL
                ↓
         Backend API
```

Backend에서는 각 기능의 내부 알고리즘을 구현하지 않고 다음 영역만 담당한다.

```text
API
DB
Persistence
상태 관리
Session
Gateway
입력 / 출력 계약
```

---

# 2. Crawler → Backend 계약 확인

Crawler 전체 수집 결과를 Backend에서 저장하는 기존 흐름을 기준으로 계약을 확인했다.

현재 전체 수집 연결은 다음과 같다.

```text
Crawler
   ↓
COLLECTION_RUNNER
   ↓
backend.app.services.collection_service:collect_and_persist
   ↓
CollectionRun
   ↓
Announcement
   ↓
Document
```

Backend 통합 브랜치의 `.env.example`에는 다음 callable을 등록했다.

```env
COLLECTION_RUNNER=backend.app.services.collection_service:collect_and_persist
```

Crawler 결과 중 Backend에서 분석 대상으로 허용하는 문서 형식은 다음과 같다.

```text
hwp
hwpx
```

Crawler 반환값과 문서 형식 계약은 Backend contract test에서 검증한다.

---

# 3. Document Processing → Backend 연결

문서 처리 기능에 실제 `document_id` 기반 재처리 함수가 추가됨에 따라 Backend Gateway와 Persistence 계약을 확인했다.

확인된 문서 재처리 callable은 다음과 같다.

```text
pipeline.document_processor:reprocess_document
```

Backend 통합 브랜치에서는 이를 다음과 같이 연결했다.

```env
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document
```

Backend 관리자 API의 문서 재처리 요청은 다음 구조로 연결된다.

```text
POST /api/admin/documents/{document_id}/reprocess
                ↓
pipeline_gateway.reprocess_document(...)
                ↓
DOCUMENT_REPROCESSOR
                ↓
pipeline.document_processor:reprocess_document
```

callable import와 Gateway loading은 로컬에서 검증했다.

---

# 4. Document storage_path 전달

문서 처리 기능은 DB에 등록된 Document의 실제 원본 파일 위치가 필요하다.

기존 `get_registered_document_context()` 결과에 실제 파일 경로가 포함되지 않았기 때문에 Backend Persistence 계약을 보완했다.

수정 대상:

```text
backend/app/services/pipeline_persistence.py
```

현재 반환 정보에는 다음 값이 포함된다.

```text
announcement_key
announcement_db_id
document_db_id
filename
format
storage_path
```

연결 구조:

```text
Document
   ↓
storage_path
   ↓
get_registered_document_context()
   ↓
document_processor
   ↓
실제 HWP / HWPX 원본 파일
```

`storage_path`가 DB에서 `NULL`인 경우 문자열 `"None"`으로 변환하지 않고 Python `None`을 반환한다.

---

# 5. ProcessingRun 실패 상태 처리

문서 처리 과정에서 Structure / Verification이 성공했더라도 이후 핵심정보 추출 또는 저장 단계에서 실패할 수 있다.

이 경우 새 ProcessingRun을 정상 데이터로 활성화하면 안 된다.

이를 위해 Backend Persistence에 다음 함수를 추가했다.

```python
mark_processing_run_failed(...)
```

실패 시 대상 ProcessingRun에는 다음 상태를 기록한다.

```text
execution_status = failed
current_stage = 실패 단계
error_stage = 실패 단계
error_code = 오류 코드
error_message = 오류 내용
finished_at = 실패 시각
is_active = false
```

## 보호 원칙

다음 데이터는 변경하지 않는다.

```text
verification_status
기존 active ProcessingRun
기존 정상 KeyInformation
```

예를 들어 Verification까지 정상적으로 완료된 뒤 핵심정보 단계에서 실패했다면:

```text
execution_status = failed
verification_status = pass
is_active = false
```

상태로 기록된다.

이미 `is_active = true`인 ProcessingRun을 실패 처리하려는 호출은 거부한다.

이 구조를 통해 신규 재처리가 실패하더라도 기존 정상 서비스 데이터를 유지할 수 있다.

---

# 6. KeyInformation 연결 확인

Backend에는 기존부터 핵심정보 저장 서비스가 존재한다.

```text
backend/app/services/key_information_service.py
```

주요 저장 진입점:

```python
upsert_key_information(...)
```

최신 문서 처리 흐름에서는 핵심정보 추출 이후 해당 Backend 저장 서비스를 사용하는 구조가 연결되었다.

정상 흐름:

```text
Document Processing
        ↓
Structure / Verification
        ↓
Chunk / Embedding
        ↓
KeyInformation Extraction
        ↓
upsert_key_information(...)
        ↓
ProcessingRun 활성화
```

핵심정보 단계가 실패하면 신규 ProcessingRun은 활성화되지 않고 `mark_processing_run_failed(...)`를 통해 실패 상태로 남는다.

Backend에서는 핵심정보 추출 알고리즘 자체를 구현하지 않는다.

---

# 7. 공통 ErrorLog Persistence

각 기능이 `ErrorLog` 테이블에 직접 서로 다른 방식으로 INSERT하지 않도록 Backend 공통 저장 진입점을 추가했다.

파일:

```text
backend/app/services/error_log_service.py
```

주요 함수:

```python
record_error(...)
```

지원하는 오류 영역:

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

`processing_run_id`가 전달되면 Backend에서 관계를 확인하여 상위 데이터를 해석한다.

```text
ProcessingRun
   ↓
Document
   ↓
Announcement
   ↓
CollectionRun
```

관련 ID가 서로 맞지 않으면 ErrorLog 저장을 거부한다.

현재 상태는 다음과 같다.

```text
Backend 공통 ErrorLog 저장 진입점 구현    완료
각 기능의 실제 오류 발생 지점 호출 연결   미완료
```

Crawler / 문서 처리 / AI 담당 기능에서는 실제 오류 발생 위치에서 `record_error(...)`를 연결할지 최종 통합 과정에서 확인해야 한다.

---

# 8. Pipeline Gateway 연결 상태

Backend Gateway에서 사용하는 외부 실행 계약은 다음과 같다.

```text
COLLECTION_RUNNER
ANNOUNCEMENT_RECOLLECTOR
DOCUMENT_REPROCESSOR
ERROR_RETRY_RUNNER
```

현재 통합 상태:

| Gateway | 상태 | 연결 |
|---|---|---|
| `COLLECTION_RUNNER` | 완료 | `backend.app.services.collection_service:collect_and_persist` |
| `DOCUMENT_REPROCESSOR` | 완료 | `pipeline.document_processor:reprocess_document` |
| `ANNOUNCEMENT_RECOLLECTOR` | 미연결 | Crawler 측 callable 필요 |
| `ERROR_RETRY_RUNNER` | 미연결 | Retry callable 필요 |

Backend API Endpoint가 존재한다고 해서 해당 외부 Runner까지 자동으로 구현된 것은 아니다.

Gateway에 실제 callable이 등록되어야 최종 실행이 가능하다.

---

# 9. Backend Contract Test

기능 간 연결 규칙이 이후 변경으로 깨지는 것을 확인할 수 있도록 Backend 통합 계약 테스트를 추가했다.

파일:

```text
tests/backend/test_backend_contracts.py
```

현재 총 테스트:

```text
18
```

주요 검증 범위:

```text
Crawler result contract
Crawler execution_id
Crawler execution_status
Crawler data type
HWP / HWPX document format
COLLECTION_RUNNER environment contract
COLLECTION_RUNNER callable invocation
RAG result → Backend ChatResponse
잘못된 RAG result 거부
ErrorLog error type
ErrorLog stage / message validation
ProcessingRun → parent relation resolution
잘못된 ErrorLog parent relation 거부
Document storage_path 전달
ProcessingRun failure 처리
verification_status 보존
기존 active ProcessingRun 보호
```

최종 로컬 실행 결과:

```text
Ran 18 tests
OK
```

추가 검증:

```text
git diff --check
PASS
```

---

# 10. 현재까지 연결된 Backend 흐름

## 10.1 공고 전체 수집

```text
Admin API
   ↓
COLLECTION_RUNNER
   ↓
Crawler
   ↓
collection_service
   ↓
CollectionRun
   ↓
Announcement
   ↓
Document
```

## 10.2 관리자 Document 재처리

```text
Admin API
   ↓
DOCUMENT_REPROCESSOR
   ↓
document_processor
   ↓
Document storage_path
   ↓
Parser / Normalizer / Structure / Verification
   ↓
Chunk / Embedding
   ↓
Backend Persistence
   ↓
KeyInformation
```

정상 완료된 신규 처리 결과만 서비스용 데이터로 활성화할 수 있다.

실패한 신규 ProcessingRun은 기존 정상 active 결과를 교체하지 않는다.

---

# 11. 이번 작업에서 수정하지 않은 영역

이번 Backend 통합 작업에서는 다음 기능 내부 로직을 수정하지 않는다.

```text
Crawler 내부 수집 알고리즘
HWP Parser
HWPX Parser
Normalizer
Structure
Verification
핵심정보 추출 알고리즘
Chunking
Embedding
Vector Search
RAG Retrieval
Prompt
LLM
Frontend
```

Backend에서는 해당 기능의 결과를 받을 수 있는 API / DB / Persistence / Gateway 계약만 관리한다.

---

# 12. 아직 남은 통합 항목

현재 Backend 통합 작업 이후에도 전체 MVP 흐름을 자동으로 연결하기 위해 남은 항목이 있다.

## 12.1 신규 Document 처리 시작

현재 관리자 API를 통한 개별 Document 재처리 callable은 연결 가능하다.

하지만 새 Collection 수집 직후:

```text
Crawler
   ↓
Document 저장
   ↓
신규 Document 자동 처리
```

에서 누가 신규 Document 처리를 시작할지는 아직 최종 연결되지 않았다.

---

## 12.2 Collection 내 전체 Document 완료 판단

Collection에 여러 Document가 존재할 수 있기 때문에:

```text
모든 Document 처리 완료
+
필요한 Chunk / Embedding 준비
+
핵심정보 준비
```

상태를 어떤 실행 주체가 판단할지 결정해야 한다.

---

## 12.3 Collection Publish 호출

Backend에는 Collection 검증 및 active 전환 로직이 존재한다.

```python
publish_collection_run(...)
```

하지만 다음 시점과 호출 주체는 최종 통합 항목으로 남아 있다.

```text
언제 publish 하는가
누가 publish_collection_run()을 호출하는가
```

수집만 완료됐다고 바로 publish하면 안 된다.

---

## 12.4 ErrorLog 실제 호출 연결

Backend의 공통 `record_error(...)`는 구현되어 있다.

하지만 각 기능의 실제 오류 처리 코드에서 호출하도록 연결하는 작업은 남아 있다.

```text
Crawler error
Document Processing error
Chunking error
Embedding error
RAG error
LLM error
```

각 담당 기능은 자기 오류 발생 위치를 알고 있으므로 해당 위치에서 Backend ErrorLog 저장 진입점을 사용할지 최종 연결해야 한다.

---

## 12.5 Announcement Recollection Runner

Backend에는 다음 관리자 API와 Gateway가 준비되어 있다.

```text
POST /api/admin/announcements/{announcement_id}/recollect

ANNOUNCEMENT_RECOLLECTOR
```

하지만 실제 Crawler 재수집 callable은 아직 연결되지 않았다.

---

## 12.6 Error Retry Runner

Backend에는 다음 관리자 API와 Gateway가 준비되어 있다.

```text
POST /api/admin/errors/{error_id}/retry

ERROR_RETRY_RUNNER
```

하지만 실제 재시도 Runner는 아직 연결되지 않았다.

---

# 13. 통합 완료 기준

Backend 기준 이번 통합에서 완료된 주요 항목은 다음과 같다.

```text
Crawler 전체 수집 callable 확인
Document 재처리 callable 연결
Pipeline Persistence 계약 보완
KeyInformation 저장 연결 확인
실패한 신규 ProcessingRun 보호
ErrorLog 공통 저장 방식 구현
Backend contract test 추가 및 통과
```

전체 서비스 관점에서는 추가로 다음 흐름이 연결되어야 한다.

```text
공고 수집
   ↓
Document 저장
   ↓
신규 Document 처리
   ↓
Chunk / Embedding
   ↓
KeyInformation
   ↓
전체 처리 완료 판단
   ↓
Collection publish
   ↓
사용자 서비스 노출
```

---

# 14. 현재 상태 요약

| 항목 | 상태 |
|---|---|
| Crawler 전체 수집 → Backend DB | 완료 |
| `COLLECTION_RUNNER` | 완료 |
| Document `storage_path` 전달 | 완료 |
| Document 재처리 callable | 완료 |
| `DOCUMENT_REPROCESSOR` | 완료 |
| Pipeline Persistence 계약 보완 | 완료 |
| KeyInformation Backend 저장 연결 | 완료 |
| 신규 ProcessingRun 실패 처리 | 완료 |
| 기존 active ProcessingRun 보호 | 완료 |
| ErrorLog 공통 저장 진입점 | 완료 |
| Backend contract test | 18 / 18 PASS |
| `ANNOUNCEMENT_RECOLLECTOR` | 미연결 |
| `ERROR_RETRY_RUNNER` | 미연결 |
| 신규 Document 자동 처리 시작 | 미연결 |
| 전체 Document 완료 판단 | 미연결 |
| Collection 자동 publish | 미연결 |
| 각 기능 → `record_error(...)` 호출 | 미연결 |
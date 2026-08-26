# Backend Integration

> 기준 시점: **2026-08-25**
> 목적: Crawler / Document Processing / RAG와 Backend API / DB 사이의 **현재 실제 연결 계약**을 기록한다.
>
> 과거 초기 통합 과정은 `docs/BACKEND_DB_INTEGRATION_HISTORY.md`를 참고한다.

---

# 1. 현재 통합 상태

초기 `feature/backend-integration` 시점과 달리 현재는 전체 수집 후 primary 문서 처리까지 연결되어 있다.

```text
Admin
→ Pipeline Gateway
→ Integration Service
→ Collection Service
→ Crawler
→ DB Persistence
→ primary Document Processing
→ Pipeline Persistence
→ KeyInformation
→ ProcessingRun Activation
```

전체 신규 수집의 현재 Publish 계약:

```text
CollectionRun.status = success
+ analysis_document_ids 처리 failed_count = 0
→ publish_collection_run(collection_run_id) 자동 호출
→ SystemState.active_collection_run_id 전환
```

Collection 실패 또는 Document 처리 실패가 있으면 Publish를 수행하지 않는다.

Publish validation / activation 실패 시 ErrorLog를 기록하고 Integration 결과를 `failed`로 반환한다.

개별 공고 재수집(`recollect`)은 새 분석 대상 Document를 처리하지만 자동 Publish하지 않는다.

---

# 2. Gateway 계약

현재 `.env.example`:

```env
COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
ANNOUNCEMENT_RECOLLECTOR=backend.app.services.integration_service:recollect_persist_and_process
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document
RAG_ANSWER_FUNCTION=rag.service:answer_question
```

미연결:

```text
ERROR_RETRY_RUNNER
```

---

# 3. 전체 수집 계약

```text
pipeline_gateway.collect_announcements()
→ COLLECTION_RUNNER
→ integration_service.collect_persist_and_process()
```

Integration Service:

```text
collect_and_persist()
→ CollectionRun / Announcement / Document 저장
→ analysis_document_ids 수신
→ process_document_ids()
```

`analysis_document_ids`:

```text
primary
+
download_status = completed
```

문서 처리:

```text
process_document_ids()
→ pipeline_gateway.reprocess_document(document_id)
→ DOCUMENT_REPROCESSOR
→ pipeline.document_processor:reprocess_document
```

---

# 4. 개별 재수집 계약

```text
POST /api/admin/announcements/{id}/recollect
→ pipeline_gateway.recollect_announcement()
→ ANNOUNCEMENT_RECOLLECTOR
→ integration_service.recollect_persist_and_process()
→ collection_service.recollect_and_persist()
→ new_analysis_document_ids
→ Document Processor
```

따라서 과거 문서의 `ANNOUNCEMENT_RECOLLECTOR 미연결` 상태는 현재와 다르다.

---

# 5. Document Processing 계약

입력:

```text
document_id
```

Backend가 제공하는 Document context:

```text
announcement_key
announcement_db_id
document_db_id
filename
format
storage_path
```

실제 원본 파일은 `Document.storage_path`를 사용한다.

현재 `DOCUMENT_REPROCESSOR`:

```text
pipeline.document_processor:reprocess_document
```

---

# 6. 문서 처리 실제 흐름

```text
Document
→ Parser
→ Normalizer
→ Structure
→ Verification
→ Chunking
→ Embedding
→ persist_document_outputs()
→ KeyInformation extraction / upsert
→ activate_processing_run()
```

Persistence 대상:

```text
ProcessingRun
DocumentStructure
ChunkSet
Chunk
Embedding
```

KeyInformation은 Structure / Verification 데이터를 기반으로 한다.

---

# 7. 실패 처리

## Document Processor 내부

Persistence 이후 단계에서 실패하면 새 ProcessingRun을 실패 상태로 남기고 기존 active run을 보호해야 한다.

Backend Persistence 함수:

```python
mark_processing_run_failed(...)
```

보호 원칙:

```text
기존 active ProcessingRun 유지
기존 정상 KeyInformation 보호
신규 실패 run is_active=false
```

## Integration Service

문서 처리 callable이 실패 결과를 반환하거나 예외가 발생하면:

```python
record_error(...)
```

를 사용해 Backend ErrorLog에 기록한다.

현재 `record_error()` 반환 key:

```text
error_id
```

---

# 8. Document Role 계약

현재:

```text
primary
supporting
unknown
```

분류 시 supporting keyword를 primary보다 먼저 판별한다.

이유:

```text
"모집공고문_QA..."
```

같은 파일을 primary로 오판하지 않기 위해서다.

실제 LH E2E에서 확인한 일반 `제출서류` 패턴도 이번 Backend/DB 최신화 브랜치에서 supporting으로 추가했다.

현재 전체 AI 처리:

```text
primary only
```

현재 supporting은 DB 저장만 하고 RAG index를 만들지 않는다.

Unknown은 Publish를 차단한다.

---

# 9. Collection Publish 계약

Service:

```text
backend/app/services/collection_publish_service.py
```

사전 검증:

```python
validate_collection_run_for_publish(id)
```

실제 Publish:

```python
publish_collection_run(id)
```

중요:

`publish_collection_run()`이 내부 validation을 다시 수행하므로 사전 검증 함수를 반드시 먼저 호출해야 하는 구조는 아니다.

전체 신규 수집 경로에서는 `collect_persist_and_process()`가 Collection 성공 및 분석 대상 Document 처리 성공을 확인한 뒤 `publish_collection_run()`을 자동 호출한다.

개별 공고 재수집 경로에서는 자동 호출하지 않는다.

Publish 결과:

```text
system_state.active_collection_run_id 변경
```

현재 Admin route에 Publish API는 없다.

---

# 10. 사용자 / RAG 연결

사용자 Announcement API:

```text
Active Collection 한정
```

RAG:

```text
Active Collection
+ 요청 announcement_id
+ active ProcessingRun
+ active ChunkSet
+ 정상 Embedding
```

관리자 조회:

```text
Active Collection 제한 없음
```

---

# 11. Admin API 통합 상태

## 조회

```text
Announcement list/detail   PASS
Document list/detail       PASS
Document download          PASS
ProcessingRun API          존재
Error list/detail          PASS
```

주의:

Backend에는 ProcessingRun API가 있지만 현재 관리자 Frontend에 별도 Processing History 페이지는 없다.

## Write / Action

```text
Admin login/session        PASS
Error status PATCH         PASS
Announcement collect       연결
Announcement recollect     연결
Document reprocess         연결
Error retry                ERROR_RETRY_RUNNER 미연결
Collection publish         Admin API 없음
```

---

# 12. AWS 실제 E2E

실제 LH 수집:

```text
Announcement 50
Document     88

primary      48
supporting   40
unknown       0
```

primary 처리:

```text
requested 48
success   48
failed     0
```

저장:

```text
Chunk      14,047
Embedding  14,047
```

Publish:

```text
CollectionRun id=1
active_collection_run_id=1
```

사용자 / 관리자 read flow와 관리자 Error status write까지 실제 확인했다.

---

# 13. 관리자 Document 재처리 Runtime 검증

`document_id=87` 단독 재처리:

```text
new ProcessingRun id=49
execution_status=succeeded
verification_status=pass
is_active=true

old ProcessingRun id=48
is_active=false
```

Parser → BGE-M3 CUDA Embedding → Persistence → KeyInformation → Activation 전체가 실제 Runtime에서 통과했다.

---

# 14. Backend / DB Contract Test

현재 `feature/backend-db-update` 핵심 suite:

```text
48 / 48 PASS
```

검증 범위:

```text
Crawler / Collection contract
Gateway callable contract
Chat response contract
ErrorLog contract
Pipeline Persistence 보호
Collection Publish
Document Role
Integration Service
```

추가한 회귀:

```text
일반 "제출서류" filename
→ supporting
```

`tests/backend` 전체 discover에 존재하는 KeyInformation `application_period` 실패 3건은 별도 영역의 기존 baseline 문제로 분리한다.

---

# 15. 현재 미완료 / 후속 항목

Backend/DB 기준:

```text
ERROR_RETRY_RUNNER 연결
Document Role 처리정책 분리
supporting 문서 RAG 포함
unknown 재분류 / 관리자 검토
문서 처리 Background Job / Queue
ProcessingRun 실제 wall-clock timestamp 개선
Collection Publish Admin API 여부 결정
Glossary DB/API
```

RAG/Chat 별도:

```text
MVP_ANNOUNCEMENT_ID 단일 공고 제한
MVP_DOCUMENT_FORMAT fallback
MVP_ANNOUNCEMENT_ID / MVP_DOCUMENT_FORMAT 운영 범위 정리 필요
llama.cpp generation blocker
```

---

# 16. 운영 정책

AWS에서 실제로 GPU 자원 경쟁을 확인했기 때문에 현재 운영은 직렬화한다.

```text
Chat 사용
→ llama.cpp ON

문서 재처리
→ llama.cpp OFF
→ reprocess
→ llama.cpp ON
```

이는 현재 코드 강제 조건이 아니라 AWS 안정성을 위한 운영 정책이다.

---

# 17. Git 운영

```text
Windows 로컬
→ 수정 / 테스트 / commit / push / PR

AWS
→ develop pull
→ Runtime 실행 / 검증
```

AWS에서는 Backend/DB 코드를 push하지 않는다.

# Backend / DB Integration History

> 기준 시점: **2026-08-25**
> 목적: Backend / DB 구현과 통합 과정에서 무엇을 바꿨고, 왜 바꿨으며, 어디까지 실제 Runtime으로 검증했는지 기록한다.
>
> 현재 코드 사용법은 `docs/BACKEND.md`, DB 구조는 `docs/DATABASE.md`, 현재 통합 계약은 `docs/BACKEND_INTEGRATION.md`를 우선한다.

---

# 1. 초기 Backend / DB 통합

주요 commit:

```text
5688c685
feat: integrate backend database persistence and admin APIs
```

주요 범위:

```text
ORM Models
Pipeline Persistence
Admin APIs
Admin authentication/session
Error status management
SystemState
KeyInformation
```

목적:

외부 Crawler / 문서 처리 / AI 기능이 서로 직접 DB를 만지지 않고 Backend Service / Persistence 계약을 통해 연결할 수 있는 기반을 만들었다.

---

# 2. Backend Contract Test

commit:

```text
083af042
test: add backend integration contract tests
```

초기 검증:

```text
Crawler result contract
HWP/HWPX format
Gateway environment callable
Chat RAG response
```

이후 ErrorLog, Persistence, Integration, Publish, Document Role 테스트가 추가되었다.

---

# 3. Document Processing Backend Contract

commit:

```text
c0da49ca
feat: complete document processing backend contract
```

주요 변경:

```text
DOCUMENT_REPROCESSOR
= pipeline.document_processor:reprocess_document
```

Document Processor가 실제 파일을 찾을 수 있도록 context에:

```text
storage_path
```

를 추가했다.

신규 처리 실패 보호:

```python
mark_processing_run_failed(...)
```

도 추가했다.

---

# 4. Backend Integration 문서화

commit:

```text
a8d9aa9
docs: add backend integration guide
```

PR:

```text
#12
feature/backend-integration
→ develop
```

이 시점 문서는 초기 통합 계약을 기록했기 때문에 이후 Integration Service / AWS E2E 상태와 차이가 생겼다.

---

# 5. Integration Service

현재 전체 수집 callable:

```text
backend.app.services.integration_service:collect_persist_and_process
```

개별 재수집:

```text
backend.app.services.integration_service:recollect_persist_and_process
```

Integration Service가 담당하는 orchestration:

```text
Collection Service
→ DB Persistence
→ analysis_document_ids
→ Document Processor
→ 실패 ErrorLog 기록
```

따라서 초기 문서의:

```text
COLLECTION_RUNNER=collection_service:collect_and_persist
ANNOUNCEMENT_RECOLLECTOR 미연결
신규 Document 처리 미연결
```

상태는 현재 기준으로 폐기되었다.

---

# 6. 실제 LH 통합 E2E

AWS GPU 서버에서 실제 LH 공고를 대상으로 실행했다.

## Collection

```text
Announcement 50
Document     88
```

Role:

```text
primary      48
supporting   40
unknown       0
```

실제 데이터에서 일반 `제출서류` filename 패턴을 supporting으로 취급해야 하는 사례를 확인했다.

---

# 7. 실제 Document Processing

분석 대상:

```text
48 primary Documents
```

결과:

```text
requested_count = 48
success_count   = 48
failed_count    = 0
```

HWP / HWPX 양쪽 Runtime 처리 확인.

저장:

```text
Chunk       14,047
Embedding   14,047
```

Embedding:

```text
BAAI/bge-m3
dimension=1024
CUDA NVIDIA L4
```

---

# 8. Publish E2E

초기 Role 분류에서 supporting 첨부파일 일부가 unknown으로 남아 Publish가 막히는 문제를 확인했다.

실제 LH filename 사례를 기준으로 supporting 분류를 보완한 뒤:

```text
primary    48
supporting 40
unknown     0
```

상태를 만들었고 Publish validation을 통과했다.

Publish:

```text
CollectionRun id=1
SystemState.active_collection_run_id=1
```

중요:

`CollectionRun`에는 `is_published`, `published_at` column이 없다.

Publish는 SystemState의 active Collection을 전환하는 동작이다.

이 AWS E2E 당시 Publish는 `collection_publish_service.py`의 Publish Service를 별도로 호출하여 검증했다.

이후 로컬 `feature/backend-integration`에 남아 있던 자동 Publish 구현을 최신 `origin/develop` 위로 rebase하면서 현재 Document Role 정책에 맞게 통합했다.

최신 통합에서는 전체 Document가 아니라 `analysis_document_ids`, 즉 `primary + download completed` 문서만 처리한다.

```text
CollectionRun.status = success
+ 분석 대상 Document 처리 failed_count = 0
→ publish_collection_run(collection_run_id) 자동 호출
```

Collection 또는 Document 처리 실패 시 Publish를 수행하지 않는다.

Publish validation / activation 실패 시 ErrorLog를 기록하고 Integration 결과를 `failed`로 반환한다.

개별 공고 재수집은 자동 Publish하지 않는다.

최신 Backend/Admin 핵심 계약 테스트:

```text
48 tests
48 PASS
```

이번에 최신 코드로 통합한 **전체 신규 수집 → Document 처리 → 자동 Publish orchestration** 전체 경로는 아직 AWS에서 다시 실행하여 Runtime 검증한 상태는 아니다.

---

# 9. 사용자 Frontend E2E

실제 Backend / DB 데이터를 기준으로 확인:

```text
공고 목록
공고 상세
KeyInformation
원문 공고 링크
```

User Vite → FastAPI → PostgreSQL 경로 확인.

---

# 10. 관리자 Frontend E2E

확인:

```text
Login / Session
Announcement list/detail
Document list/detail
HWP/HWPX download
Error list/detail
Error status PATCH
```

Backend에 `/api/admin/processing-runs` route는 존재하지만 관리자 Frontend에 별도 화면은 없다.

Collection Publish용 Admin API도 현재 없다.

---

# 11. Document Reprocess Incident 조사

관리자 재처리는 현재 동기 HTTP 요청이다.

정적 코드 흐름:

```text
Admin POST
→ pipeline_gateway
→ Document Processor
→ subprocess 기반 단계 실행
→ Persistence
→ KeyInformation
→ Activation
```

한 번의 재처리 과정에서 서버 관리 측 재부팅과 시점이 겹친 사건이 있었지만,
guest log에서는 OOM / NVRM Xid / segfault / panic 등 명확한 crash 근거가 확인되지 않았다.

따라서 해당 사건을 `재처리가 서버를 확정적으로 다운시켰다`고 기록하지 않는다.

---

# 12. Controlled Reprocess Retest

위험을 줄이기 위해 llama.cpp를 중지하고 `document_id=87`을 단독 재처리했다.

결과:

```text
ProcessingRun 49
document_id=87
execution_status=succeeded
verification_status=pass
is_active=true
```

기존:

```text
ProcessingRun 48
is_active=false
```

GPU Embedding 종료 후 VRAM도 반환됐다.

결론:

```text
Isolated Document Reprocess = PASS
```

현재 운영은 GPU workload를 직렬화한다.

---

# 13. ProcessingRun Timestamp 확인

현재 `ProcessingRun` DB row는 실제 Pipeline 시작 전에 생성되지 않고 Persistence 단계에서 생성된다.

따라서:

```text
started_at
finished_at
```

은 현재 전체 Parser → Embedding wall-clock 시간을 정확히 표현하지 않는다.

후속 비동기 Job 구조에서 개선할 항목이다.

---

# 14. 2026-08-25 GitHub 최신화 브랜치

작업 브랜치:

```text
feature/backend-db-update
```

branch creation base:

```text
develop
afa64e46c5e9c8caa01a8e29ab19de998ecec818
```

이번 코드 수정:

```text
backend/app/services/document_role_service.py
tests/backend/test_document_role_service.py
```

변경:

```text
일반 "제출서류"
→ DOCUMENT_ROLE_SUPPORTING
```

회귀 테스트 추가:

```text
붙임_제출서류양식.hwpx
→ supporting
```

검증:

```text
Document Role tests 12 / 12 PASS
Backend / DB core tests 42 / 42 PASS
git diff --check PASS
```

Alembic:

```text
7564ce797c61 (head)
```

Schema 변경이 없으므로 이번 수정에는 Migration을 추가하지 않는다.

---

# 15. 전체 Backend Test Baseline

현재 develop 기준:

```text
python -m unittest discover -s tests/backend -p "test_*.py" -v
```

결과:

```text
Ran 49
failures = 3
```

실패는 모두:

```text
test_key_information_extractor
application_period
```

영역이다.

이번 Document Role 수정과 무관하며, 현재 develop의 KeyInformation 날짜/시간 normalization 기대값과 실제 구현 사이의 기존 불일치로 별도 처리한다.

따라서 Backend/DB 이번 PR의 회귀 판단은 Backend/DB core 42/42 PASS를 기준으로 한다.

---

# 16. 현재 확인된 기술부채

## Backend / DB

```text
Document Role이 파일명 hardcoding 중심
Role과 Processing Policy가 결합
supporting RAG 미처리
unknown 자동 재분류 없음
문서 재처리 synchronous HTTP
ProcessingRun wall-clock timestamp 의미 부족
Collection Publish Admin API 없음
ERROR_RETRY_RUNNER 미연결
```

## RAG / Chat 별도

```text
MVP_ANNOUNCEMENT_ID
MVP_DOCUMENT_FORMAT
MVP_ANNOUNCEMENT_ID / MVP_DOCUMENT_FORMAT 운영 범위 정리 필요
llama.cpp generation 응답 구조 문제
```

RAG/Chat 항목은 Backend/DB 브랜치에서 임의 수정하지 않는다.

---

# 17. 후속 방향

Document 분류:

```text
파일명 단일 규칙
→ source metadata + filename + 공고 제목 관계 + 순서
→ 필요 시 문서 초기 text/title
```

저장을 검토할 정보:

```text
role_classification_source
role_confidence
role_classifier_version
role_classification_reason
```

Processing:

```text
document_role
≠
processing policy
```

운영:

```text
synchronous HTTP reprocess
→ Job ID
→ Background Worker / Queue
→ 상태 polling
→ concurrency control
```

---

# 18. Git / AWS 운영 규칙

Git 변경:

```text
Windows local
→ modify
→ test
→ commit
→ push
→ PR
```

AWS:

```text
develop pull
→ run
→ E2E verify
```

AWS 서버에서는 Git push를 기준 운영으로 사용하지 않는다.

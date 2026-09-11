# Backend / DB AWS Runtime Validation - 2026-08-26

> 기준 코드: `develop` / merge commit `476575c`
>
> 검증 환경: AWS EC2 GPU 서버
>
> 목적: Backend / DB 최신 통합 코드의 실제 전체 수집, 문서 처리, 자동 Publish, API 조회 경로를 Runtime으로 검증한 결과를 기록한다.

---

## 1. Backend / Admin 계약 테스트

AWS에서 최신 `develop` 반영 후 핵심 테스트를 실행했다.

- Backend / Admin core tests: 48 / 48 PASS
- Collection Publish contract: PASS
- Document Role contract: PASS
- Integration Service contract: PASS
- Admin API contract: PASS

환경 callable도 정상 연결됐다.

- COLLECTION_RUNNER = `backend.app.services.integration_service:collect_persist_and_process`
- ANNOUNCEMENT_RECOLLECTOR = `backend.app.services.integration_service:recollect_persist_and_process`
- DOCUMENT_REPROCESSOR = `pipeline.document_processor:reprocess_document`

---

## 2. 전체 신규 수집 + Document Processing

실제 LH 공고 전체 수집 결과:

- CollectionRun ID: 2
- execution_id: `execution_20260826_004653`
- Collection status: success
- Announcement: 50
- Document: 86
- primary: 48
- supporting: 38
- unknown: 0

primary 분석 대상 처리 결과:

- requested: 48
- success: 48
- failed: 0
- error_ids: 없음

전체 실행 시간:

- elapsed_seconds: 2072.99
- 실제 wall-clock: 약 34분 35초

---

## 3. Processing / Chunk / Embedding

CollectionRun 2의 active 데이터 확인 결과:

- active ProcessingRun: 48
- execution_status: succeeded
- verification_status: pass
- active ChunkSet: 48
- ChunkSet status: completed
- Chunk: 13,863
- Chunk status: completed
- Embedding: 13,863
- Embedding status: completed
- dimension: 1024
- normalized: true

primary 48건 모두 정상 처리됐고, 서비스에 사용할 active ProcessingRun / ChunkSet도 정상 활성화됐다.

---

## 4. 자동 Publish Runtime 검증

이번 검증에서는 Publish Service를 별도로 수동 호출하지 않았다.

실제 실행 경로:

1. `collect_persist_and_process()`
2. 전체 Collection 저장
3. primary 48건 Document Processing
4. 처리 실패 0건 확인
5. `publish_collection_run(collection_run_id)` 자동 호출
6. active Collection 전환

결과:

- publish status: published
- previous_collection_run_id: 1
- active_collection_run_id: 2
- Publish 관련 ErrorLog: 0건

DB에서도 `system_state.active_collection_run_id = 2`를 독립적으로 확인했다.

따라서 최신 Integration Service의 전체 수집 후 자동 Publish orchestration은 AWS Runtime 검증 완료 상태다.

---

## 5. 사용자 API Smoke Test

Backend 상태:

- FastAPI port: 18000
- `/api/health`: HTTP 200

Active Announcement API:

- `/api/announcements?page=1&size=100`
- total: 50
- items: 50

API가 반환한 Announcement ID와 CollectionRun 2에 속한 DB Announcement ID를 비교한 결과:

- API count: 50
- DB count: 50
- exact_id_match: true
- missing_from_api: 없음
- unexpected_in_api: 없음

상세 API 검증:

- announcement_id: 51
- HTTP status: 200
- collection_run_id: 2
- Document 연결: 정상
- KeyInformation extraction_status: completed

검증한 KeyInformation 항목:

- applicationPeriod
- eligibility
- supplyInformation
- incomeAssetCriteria
- requiredDocuments
- winnerAnnouncement
- contactInformation

모두 데이터가 존재했다.

---

## 6. Admin API Smoke Test

실행 중인 FastAPI OpenAPI에서 `/api/admin/*` 경로 16개를 확인했다.

주요 API:

- `/api/admin/announcements`
- `/api/admin/documents`
- `/api/admin/processing-runs`
- `/api/admin/errors`

미인증 상태에서 위 API를 호출한 결과:

- HTTP 401
- 관리자 로그인이 필요합니다.

따라서 Admin route 등록과 인증 경계도 Runtime에서 정상 확인했다.

---

## 7. CollectionRun 1 / 2 데이터 비교

Collection 간 공고 비교:

- Collection 1 only: 2
- Collection 2 only: 2
- 공통 Announcement: 48

Collection 간 문서 비교:

- Collection 1 Document: 88
- Collection 2 Document: 86
- 공통 Document: 83
- 동일 공고 + 동일 파일명에서 checksum 변경: 0

Collection 1에서 빠진 문서:

- primary 2
- supporting 3
- 합계 5

Collection 2에서 새로 들어온 문서:

- primary 2
- supporting 1
- 합계 3

따라서:

- Document: 88 → 86
- supporting: 40 → 38

변화는 동일 공고의 첨부파일 수집 누락 정황이 아니라, 수집 시점 사이에 대상 공고 50건 구성이 2건 OUT / 2건 IN으로 변경된 결과다.

---

## 8. 전체 수집 중복 처리 고도화 항목

현재 개별 공고 재수집은 동일 filename + checksum 문서를 재사용하며 새 분석 대상 문서만 처리한다.

반면 전체 신규 Collection 수집은 이전 Collection과 동일한 파일이어도 새 snapshot의 primary 문서를 다시 처리한다.

이번 Collection 비교에서:

- 공통 Announcement: 48
- 공통 Document: 83
- 공통 primary: 46
- 공통 문서 checksum 변경: 0

이었지만 Full Collection에서는 primary 48건을 다시 처리했다.

후속 고도화에서는 다음 정책을 검토한다.

1. 이전 active Collection과 `source_announcement_id` 기준 공고 매칭
2. 원격 첨부파일 식별정보 비교
3. 동일성이 확정되면 다운로드 생략
4. 확정할 수 없으면 다운로드 후 SHA-256 checksum 비교
5. 동일 파일이면 Parser / Structure / Chunk / Embedding 재처리 생략
6. 신규 또는 변경된 파일만 다시 처리
7. 기존 ProcessingRun / ChunkSet / Chunk / Embedding을 새 Collection에서 재사용하는 DB 구조 설계

이 항목은 현재 구현 범위가 아니라 후속 고도화 대상으로 유지한다.

---

## 9. 최종 판정

2026-08-26 기준 Backend / DB Runtime 검증 결과:

- 최신 develop AWS 반영: PASS
- Backend / Admin core tests 48 / 48: PASS
- 전체 LH 수집 50 / 50: PASS
- primary Document Processing 48 / 48: PASS
- Chunk 13,863: PASS
- Embedding 13,863: PASS
- 자동 Publish: PASS
- active Collection 1 → 2 전환: PASS
- 사용자 Announcement API: PASS
- 사용자 Detail / Document / KeyInformation: PASS
- Admin API route / 인증: PASS
- Collection 간 데이터 차이 정합성 확인: PASS

Backend / DB 전체 수집 → 문서 처리 → 데이터 활성화 → 자동 Publish → 사용자 API 조회 경로는 AWS Runtime에서 정상 동작하는 것으로 확인했다.

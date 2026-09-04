# 전체수집 구조 복원 상세 작업 기록 및 후속 작업 인수인계

작성일: 2026-09-04 (Asia/Seoul)

문서 성격: 구현 사실, 검증 결과, 운영 주의사항, 다음 단계 제안의 구분 기록.
이 문서의 후속 설계 항목은 **아직 구현하거나 운영에 적용한 내용이 아니다.**

로컬 저장소: `C:\feature_front\one-cycle`
아래 파일 표의 경로는 팀원 환경에서도 비교할 수 있도록 저장소 루트 기준으로 기재한다.
간략 운영 안내는 `docs/FULL_COLLECTION_RESTORE.md`를 함께 참고한다.

## 1. 현재 상태 요약

| 구분 | 기록 시점 상태 |
| --- | --- |
| 작업 브랜치 | `fix/restore-full-collection` |
| 복원 브랜치 시작점 | 원격 확인한 `origin/develop-api`, `4df342a` |
| 이전 중간 수정본 | `backup/frontend`의 보존용 커밋 `5d47338` |
| 최종 복원 코드 | 구현·로컬 검증 완료, `fix/restore-full-collection` 브랜치로 인계 |
| 운영 AWS 변경 | 배포·DB 변경·운영 파일 정리 모두 미실시 |
| 1단계 | 전체수집 구조 복원, 필수 최신 기능 유지, 로컬 검증 완료 |
| 운영 적용 완료 여부 | 미완료: 팀 코드 검토와 실제 환경 종단 검증 필요 |
| 2단계 | 활성/직전 정상 Run 보관, 오래된 데이터 정리, 운영 롤백 기능 미구현 |

이번 문서화 작업에서는 기능 코드를 추가로 수정하거나 테스트를 재실행하지 않았다.
테스트 수치는 직전 구현 작업에서 실제 실행한 결과다.

## 2. 배경과 방향 변경

### 2.1 증분 방식에서 문제가 된 점

기존 증분 수집은 정기 실행마다 새 CollectionRun을 만들기보다 현재 활성 Run에
신규·수정·정정 공고를 추가하고 일부 기존 공고의 노출 여부를 변경했다.

이 구조에서는 다음 두 기준이 섞였다.

- 서비스 대상: 현재 LH 목록 1페이지의 공고.
- 데이터 활성화 단위: 한 번 수집한 결과 묶음인 CollectionRun.

현재 페이지에 없는 과거 공고가 활성 Run에 남거나, 수정 공고의 구버전이 같은 Run에
누적될 수 있어 보관·삭제·복구 정책을 별도로 복잡하게 설계해야 했다.
팀은 발표 일정과 운영 단순성을 고려해 증분 수집을 사용하지 않기로 결정했다.

### 2.2 먼저 만들었던 중간 수정본

최신 구조에서 증분 실행을 막고 전체수집 호출을 연결했다. 당시 증분 서비스와 Scan API는
남아 있었고, 관리자 Sync API는 410으로 차단했다. 파일 저장도 체크섬 버전 구조를 유지했다.

이 중간 결과는 팀이 원한 ‘증분 이전 구조 복원’과 달랐지만 다음 안전장치는 재사용했다.

- 전체수집을 실행하는 Scheduler.
- 예약/수동 전체수집이 공유하는 PostgreSQL 잠금.
- 중복 관리자 전체수집 요청에 대한 409 응답.
- 실패·중복 실행 로그와 관련 테스트.

### 2.3 최종 합의와 실제 작업 방법

최신 develop-api에서 새 브랜치를 만든 뒤 과거 파일을 복원 원본으로 사용했다.
과거 커밋에서 분기한 브랜치를 그대로 병합하거나 최신 브랜치를 강제로 과거로 이동하지 않았다.
증분 전용 코드는 실제 삭제하고 이후 필요한 기능은 유지하거나 기능 단위로 접목했다.

| 기준 커밋 | 역할 |
| --- | --- |
| `153a814` | Backend–Crawler HTTP 연동, DB 저장, 문서 연동, Publish 참고 |
| `31d7b38` | 증분 직전 Crawler 전체수집 및 목록 DOM 복원 대기 기준 |
| `5c5fff6` / `8a9910c` | 제거할 증분 구현 및 PR #110 병합 이력 식별 |
| `b0f88fa` | 지역 표시·다운로드 기능 보존 기준 |
| `dc5d52e` | 단계별 재시도·특정 첨부파일 재수집 기능 보존 기준 |
| `853bb43` / `a4bd58a` | 문서 자동 재시도 구현 및 문서화 보존 기준 |
| `5d47338` | 이번 복원 전에 만든 Scheduler·잠금·409 중간 결과 보존 |

`153a814..31d7b38`에서 변경된 파일이 Crawler, LLM Dockerfile, 평가 코드/Compose의
5개뿐이며 Backend·DB 파일은 동일함을 Git으로 확인했다.

## 3. 복원 후 전체 실행 흐름

```text
12:00 / 15:00 / 18:00 Scheduler 또는 관리자 수동 전체수집
  → collect_announcements()
  → 공통 PostgreSQL advisory lock 획득
  → COLLECTION_RUNNER의 collect_persist_and_process()
  → Crawler POST /v1/crawl-jobs
  → 공통 상태 API를 통해 작업 완료 확인 / 결과 조회
  → 새 CollectionRun → Announcement → Document 저장
  → 분석 대상 문서 처리 (실패 시 기존 자동 재시도)
  → 처리 결과와 청크·임베딩 검증
  → 성공하면 active_collection_run_id 전환
  → 잠금 해제
```

중요한 실행 순서: 현재 구현은 **Crawler 작업 결과를 받은 뒤** Backend가 새 CollectionRun을
저장한다. Crawler 다운로드가 시작되는 순간부터 DB에 running Run이 먼저 생성되는 구조를
새로 만든 것은 아니다. 실시간 수집 진행률이나 시작 시점 Run 등록은 별도 요구사항이다.

### 3.1 ‘전체’와 ‘성공’의 정확한 범위

- LH 목록 **1페이지의 공고 전체**가 대상이다. 사이트 전체 페이지를 순회하지 않는다.
- 목록 DOM 복원을 기다리며 공고 상세에 순차 진입한다.
- 기존 ID/메타데이터와 같다는 이유로 상세 진입이나 다운로드를 생략하지 않는다.
- 지원 문서 형식은 기존 HWP/HWPX다. 모든 첨부 확장자를 처리하는 기능은 아니다.
- 지원 문서의 다운로드 결과를 Document로 기록한다. 다운로드 실패 기록도 포함될 수 있다.
- AI 분석은 `primary`이면서 다운로드가 완료된 문서만 대상으로 한다.
- `supporting`은 분석하지 않는다. 분석 대상이 없는 공고는 기존 metadata-only 정책을 따른다.
- 수집 상태가 success여야 하고, 분석 대상 처리에 실패가 없어야 하며, 기존 Publish 검증까지
  통과해야 새 Run을 서비스한다.

### 3.2 실패 시 상태

| 상황 | 현재 동작 |
| --- | --- |
| 다른 전체수집이 진행 중 | 관리자 409, Scheduler는 중복 실행을 건너뜀 |
| Crawler 부분 수집·실패 | 새 Run의 Publish를 하지 않음 |
| 빈 수집 결과 | 기존 Publish 기준상 전환하지 않음 |
| primary 처리 재시도 후 최종 실패 | 새 Run의 Publish를 하지 않음 |
| 청크/임베딩 검증 실패 | Publish 실패 기록, 기존 활성 Run 유지 |
| 전체 성공 | 활성 Run 포인터를 새 Run으로 변경 |

서비스 대상이 새 Run으로 바뀌어도 이전 DB 행·원본·파이프라인 산출물은 남는다.
**전체교체와 물리 삭제는 다른 작업**이며, 현재 디스크 사용량이 자동으로 제한되는 것은 아니다.

## 4. 파일별 변경 내역

### 4.1 운영 코드와 설정

| 파일 | 변경 내용 / 이유 |
| --- | --- |
| `crawler/crawler.py` | `31d7b38` 전체수집·저장·정리 구조 복원. 목록 전용 Scan/manifest/버전 저장 제거. target 파일 재시도, 실행 ID 충돌 방지, 경로 안전 처리 접목 |
| `crawler/main.py` | Scan 작업 생성·실행 제거. 전체수집/개별 재수집과 공통 상태·결과 API 유지 |
| `backend/app/clients/crawler_client.py` | Scan Client 제거. HTTP 전체수집 및 target filename 전달 유지 |
| `backend/app/scheduler.py` | 전체수집 Gateway 호출, 12·15·18시 유지, 실패와 중복 실행 구분 |
| `backend/app/services/pipeline_gateway.py` | 전체수집 공통 잠금 유지, 증분 Gateway 제거 |
| `backend/app/api/routes/admin.py` | Sync Route 삭제, 전체수집 409 처리 유지 |
| `backend/app/services/collection_sync_service.py` | 증분 서비스 파일 삭제 |
| `backend/app/services/announcement_service.py` | 공고 조회의 `a.is_visible IS TRUE` 조건 3곳 제거 |
| `backend/app/models/announcement.py` | 증분 전용 ORM 매핑 제거. 기존 일반 공고 필드·관계 유지 |
| `backend/app/services/collection_service.py` | 증분용 대상 override 제거, 재수집 파일 중복 정리/복구, 전체수집 다운로드 오류의 ErrorLog 연결 |
| `backend/app/services/recollection_storage.py` | 신규 파일. 재수집 경로·실제 체크섬 검증 전담 |
| `backend/app/services/integration_service.py` | 증분용 override 제거. 신규 primary와 원본 복구 primary를 처리하도록 연결. 자동 재시도 유지 |
| `backend/app/core/config.py` | 증분 로그용 document_storage_root 제거. 공유 Crawler 경로 설정 사용 |
| `.env.example` | 폐기 설정 제거, CRAWLER_STAGING_DIR 공유 설정 설명 |
| `infra/docker-compose.yml` | Backend/Scheduler에도 CRAWLER_STAGING_DIR=/data/documents 전달. 기존 서비스 분리·볼륨 유지 |

단계별 재시도 구현이 들어 있는 Document Worker, Frontend, RAG 파일과 기존 Publish 서비스,
기존 마이그레이션 파일은 이번 복원에서 수정하지 않았다. 기능이 이미 최신 작업 기준에
포함돼 있었으므로 통째로 다시 Cherry-pick할 필요가 없었다.

### 4.2 증분 필드 정리의 범위

제거한 공고 실행 코드/ORM 매핑: `is_visible`, `normalized_title`, `metadata_hash`,
`change_type`, `supersedes_announcement_id`, `last_seen_at`.

DB의 실제 컬럼은 남아 있다. `pipeline_persistence.py`에서 쓰는 Chunk metadata의
`normalized_title`은 이름만 같은 기존 문서 구조 정보이므로 제거하지 않았다.

### 4.3 테스트와 문서

| 파일 | 역할 |
| --- | --- |
| `tests/backend/test_collection_sync_service.py` | 삭제한 증분 전용 테스트 |
| `tests/test_crawler_scan.py` | 삭제한 목록 전용 Scan 테스트 |
| `tests/backend/test_crawler_client.py` | Scan 테스트 제거, 공통 HTTP 계약 유지 |
| `tests/test_crawler_api.py` | Scan 대신 전체수집·재수집 공통 조회, busy/실패 상태와 Scan Route 부재 검사 |
| `tests/backend/test_scheduler.py` | 전체수집 시간·콜백·실패·중복 동작 |
| `tests/backend/test_backend_contracts.py` | 공통 잠금을 사용하는 Gateway 계약에 맞춰 격리 |
| `tests/backend/test_full_collection_policy.py` | 전체수집 전환·실패 유지·잠금·API·Publish 검증·자동 재시도 |
| `tests/backend/test_recollection_storage.py` | 실제 임시 파일을 사용하는 중복·복구·변경·안전성·오류 연결 |
| `tests/test_crawler_full_collection.py` | 1페이지 순회·DOM 복원·실행별 저장·임시 폴더 정리 |
| `tests/backend/test_collection_lock_postgres.py` | 실제 PostgreSQL과 별도 프로세스의 양방향 잠금 검증 |
| `tests/backend/test_collection_publish_postgres.py` | 실제 DB의 Publish·공고 조회·벡터/BM25 범위 검증 |
| `docs/INCREMENTAL_CRAWLING.md` | 삭제한 증분 운영 문서 |
| `docs/FULL_COLLECTION_RESTORE.md` | 현재 운영 요약·검증·배포 주의사항 |
| `docs/FULL_COLLECTION_HANDOFF_20260904.md` | 이 상세 작업 기록과 후속 계획 |

삭제한 추적 파일은 Git 이력으로 복구할 수 있다. AWS 운영 파일을 삭제한 작업은 아니다.

## 5. 파일 저장 및 다운로드 재시도 상세

### 5.1 새 저장 구조

```text
공유 다운로드 루트/
  execution_<timestamp>_<unique>/
    _temp_download/          ← 해당 실행 종료 시 정리
    공고A/공고문.hwpx        ← 보존
    공고B/공고문.hwpx        ← 보존
  recollect_<timestamp>_<unique>/
    _temp_download/          ← 해당 실행 종료 시 정리
    공고A/공고문.hwpx        ← DB 재사용 판정에 따라 보존 또는 새 중복본만 정리
```

일반 공고 ID는 경로 구성요소로 사용한다. 안전하지 않은 문자를 포함한 ID는 해시 기반
구성요소로 변환해 경로 이탈과 정규화 충돌을 방지한다. 같은 파일명이라도 공고별로 분리한다.
실행 ID의 고유 suffix는 같은 초에 실행된 작업의 경로 충돌을 방지한다.

### 5.2 동일 파일을 재수집했을 때

중복 판단은 **동일 Announcement 내부의 파일명+체크섬**이다. 모든 공고 또는 모든 Run을
통틀어 동일 체크섬 문서를 재사용하는 정책이 아니다.

1. 새 다운로드 경로가 현재 재수집 실행/공고/파일에 속하는지 확인한다.
2. 실제 파일의 SHA-256이 결과에 기록된 체크섬과 일치하는지 확인한다.
3. 기존 Document의 파일이 존재하고 내용도 일치하면 기존 Document와 경로를 유지한다.
4. DB 저장이 성공한 뒤 새 중복 파일을 정리한다.
5. 정리 직전에 기존 파일과 DB 참조를 다시 확인한다.

기존 파일이 사라졌거나 내용이 일치하지 않으면 기존 Document의 경로를 새 다운로드 파일로
복구한다. primary라면 `recovered_analysis_document_ids`에 넣어 다시 처리한다.
기존 파일 자체를 지우거나 이동하지는 않는다.

체크섬이 다르면 새 Document를 만들고, 분석 대상이면 기존 문서 처리 경로로 전달한다.
기존 Document를 일괄 삭제하는 기능은 추가하지 않았다.

### 5.3 안전장치와 현재 한계

- 새 중복 파일 삭제는 현재 재수집 실행 경로에 한정한다.
- 기존 체크섬 버전 저장 경로의 파일은 삭제 대상이 아니다.
- 심볼릭 링크/경로 이탈/체크섬 불일치가 확인되면 안전하지 않은 파일 작업을 거부한다.
- DB 저장 실패 시 새 파일을 먼저 삭제하지 않는다.
- 다른 Document가 참조하는 새 경로는 삭제하지 않는다.
- 파일 정리의 OSError/ValueError는 로그와 `duplicate_cleanup_errors`에 남긴다.
- 모든 DB·파일시스템 장애가 자동 복구된다는 의미는 아니다. 현재 정리 실패를 재실행하는
  별도 백그라운드 작업이나 관리자 UI 표시는 구현하지 않았다.
- DB 저장 이후 프로세스가 종료되면 새 중복 파일이 남을 가능성이 있다. 빈 실행 디렉터리와
  DB에 등록되지 않은 파일을 일괄 정리하는 정책도 아직 없다.

### 5.4 전체수집 오류와 관리자 재시도 연결

전체수집 결과를 DB에 먼저 저장한 후 Crawler 오류의 source ID/파일명을 해당 회차의
Announcement/Document ID와 연결해 ErrorLog를 생성한다. `target_filename`을 기록하므로
기존 관리자 오류 재시도가 특정 첨부파일을 지정할 수 있다.

단, source ID나 파일명이 없는 상위 수집 오류는 개별 파일 재시도의 대상 정보를 만들 수 없다.
이런 오류까지 특정 파일 재시도가 가능하다고 가정하면 안 된다.

## 6. Scheduler·잠금·재시도의 정확한 보장 범위

### 6.1 Scheduler 설정

- 시간대: Asia/Seoul.
- cron: 12, 15, 18시의 0분.
- 작업 ID: `lh_full_announcement_collection`.
- `max_instances=1`, `coalesce=True`, `misfire_grace_time=600` 유지.
- 함수명 `run_scheduled_sync()`는 호환성을 위해 남지만 수행 내용은 전체수집이다.
- 실패 결과/예외를 로그에 남기며 중복 실행은 구분해 건너뛴다.

시간이 겹쳐 건너뛴 전체수집을 반드시 나중에 한 번 더 실행하는 별도 큐는 없다.
3회 시각 설정과 ‘매일 반드시 3회 성공’은 같은 보장이 아니다.

### 6.2 공통 DB 잠금

`pg_try_advisory_lock(615120315)`을 별도 DB 연결에서 획득하고 전체 callable 종료까지 유지한다.
전용 연결은 AUTOCOMMIT으로 설정해 처리 시간 동안 열린 idle transaction을 유지하지 않는다.
해제 실패 또는 잠금 획득 상태가 불확실한 연결은 풀에 정상 반환하지 않도록 invalidate한다.

이 잠금은 `collect_announcements()`를 통과하는 **예약·관리자 전체수집**을 보호한다.
개별 재수집, 문서 재처리, 직접 Publish 호출, 향후 삭제 작업까지 모두 같은 잠금으로
직렬화된 것은 아니다. Crawler의 busy 검사 역시 크롤링 작업 범위이지 전체 AI 처리 범위가 아니다.

따라서 2단계 삭제·롤백은 기존 잠금만 있으면 안전하다고 가정하지 말고, 개별 재시도와의
경합을 포함해 별도 검토해야 한다. DB 연결 단절·프로세스 강제 종료에 대한 장기 운영 장애
주입 검증도 이번 6개 정상 제어 테스트의 범위를 넘는다.

### 6.3 자동 재시도와 재-Publish

기존 Backend 자동 재시도 설정의 기본값은 총 3회 시도, 시도 사이 5초 대기다.
인식 가능한 실패 단계는 그 단계부터 재개하고, 판단할 수 없는 경우 기존 처음부터 재시도
동작을 유지한다. 실제 동작은 배포 환경 설정값에 따른다.

자동 재시도는 **문서 처리**에 대한 것이다. 모든 Crawler 다운로드 실패의 자동 재다운로드를
새로 구현한 것은 아니다. 다운로드 실패는 현재 관리자 대상 파일 재시도 경로를 유지한다.

개별 재수집 함수는 문서 처리를 수행하지만 CollectionRun 전체를 자동으로 다시 Publish하지
않는다. 특히 수집 당시 partial이었던 Run의 집계 상태를 자동 success로 고치는 기능은 없다.
따라서 파일 재시도 성공만으로 실패한 회차가 자동 공개된다고 설명하면 안 된다.
운영 복구는 다음 정상 전체수집으로 새 Run을 만드는 방식부터 사용하고, 동일 회차 재검증·
재-Publish를 지원할지는 팀이 별도 결정해야 한다.

## 7. DB 및 기존 파일 호환성

### 7.1 변경하지 않은 것

- `c4b2e71a9d10`: 증분 필드 추가 마이그레이션.
- `8f4d1c2a7b90`: ErrorLog 대상 파일명 마이그레이션.
- AWS에 적용된 마이그레이션 이력과 기존 컬럼.
- 기존 Publish 검증 서비스.
- 기존 Document Worker, Frontend, RAG 구현.

ORM 매핑 제거는 실제 DB 컬럼 DROP과 다르다. DB 컬럼의 기본값은 남아 있다.
이 상태에서 Alembic autogenerate가 제안하는 DROP을 검토 없이 적용하면 안 된다.
컬럼 정리는 1단계 배포와 분리한 신규 마이그레이션으로만 논의한다.

### 7.2 파일 접근 설정

Crawler·Backend·Scheduler는 같은 실제 파일을 동일한 컨테이너 경로로 볼 수 있어야 한다.
Compose의 공통 값은 `CRAWLER_STAGING_DIR=/data/documents`이며 기존 공유 볼륨을 유지한다.
기존 `DOCUMENT_STORAGE_ROOT`는 더 이상 실행 코드에서 사용하지 않는다.

로컬 네이티브 실행 시 Crawler에도 직접 동일한 환경변수를 전달해야 한다.
Backend의 `.env` 로딩만으로 별도 Crawler 프로세스 설정까지 전달되지는 않는다.
Worker 역시 기존 공유 경로의 원본을 읽을 수 있어야 한다.

## 8. 검증 기록

### 8.1 실제 실행 결과

| 검증 | 결과 | 범위 제한 |
| --- | --- | --- |
| 전체 pytest, PostgreSQL 옵션 활성화 | 210 passed / 4 failed, 15 subtests passed | 기존 실패 4개 잔존 |
| 별도 프로세스 DB 잠금 | 6개 통과 | 실제 DB/프로세스, 느린 외부 pipeline은 모의 처리 |
| PostgreSQL Publish·RAG | 2개 통과 | 실제 스키마·pgvector·검색 SQL, 합성 문서/벡터 |
| 기존 마이그레이션 적용 | `8f4d1c2a7b90 (head)` | 새 테스트 DB에만 적용 |
| Backend/Scheduler 이미지 빌드 | 통과 | 별도 테스트 태그 |
| Crawler 이미지 빌드 | 통과 | 별도 테스트 태그 |
| Docker HTTP health | Backend DB connected / Crawler ok | 실제 LH·Worker 종단 처리 아님 |
| 정적 검사 | 변경 Python 치명적 문법/이름 오류 없음, diff 공백 검사 통과 | 저장소 전체 lint 규칙이 전부 통과했다는 의미는 아님 |

### 8.2 실패 4개

파일: `tests/backend/test_key_information_extractor.py`

- `test_application_period`
- `test_application_period_korean_ampm_range`
- `test_application_period_labeled_range`
- `test_supply_summary_is_compact`

앞의 3개는 테스트가 기대하는 신청기간 시간 정보와 실제 추출 결과가 다르고,
마지막은 공급정보 요약 결과가 기대와 다르다. 수정 전부터 재현됐으며 이번 작업에서
테스트를 지우거나 기대값을 낮춰 통과 처리하지 않았다. 문서 처리 담당의 별도 확인이 필요하다.
전체 테스트가 완전 녹색인 상태는 아니다.

### 8.3 환경과 재현

실행에 사용한 Python 가상환경:
`C:\Users\PC2412\AppData\Local\Temp\one-cycle-codex-venv\Scripts\python.exe`

이는 이 노트북의 임시 테스트 환경이며 팀원 공통 경로가 아니다. 팀원은 별도 테스트 환경을
구성해야 한다. Backend/Crawler 요구사항 외 pytest와 테스트 클라이언트·Worker import에
필요한 의존성도 준비해야 하며, 공통 테스트 의존성 파일 정리는 후속 과제다.

```bash
python -B -m pytest tests -q -p no:cacheprovider
```

실제 DB 테스트는 `ONE_CYCLE_TEST_POSTGRES_URL`을 지정해야 한다. 지정하지 않으면 DB 전용
8개 검증은 skip된다. URL은 loopback 호스트, DB 이름은 `restore_test` 접두사여야 한다.
운영 DB URL을 테스트에 넣지 않는다.

새 테스트 DB는 기존 `infra/postgres/init/01-enable-vector.sql`의 vector 확장을 먼저
활성화하고 기존 마이그레이션을 head까지 적용해야 한다. 이미지에 pgvector가 설치돼 있어도
DB별 `CREATE EXTENSION`이 필요하며, 이번 테스트도 이 초기화 절차를 적용했다.

### 8.4 테스트 후 정리

- 이번에 만든 테스트 Backend/Crawler/PostgreSQL 컨테이너 3개는 종료·자동 제거했다.
- 원래 실행 중이던 다른 Docker 컨테이너는 건드리지 않았다.
- `onecycle-restore-backend:test`, `onecycle-restore-crawler:test` 이미지는 로컬에 남겼다.
- 테스트에서 생성한 DB 데이터는 운영 데이터가 아니며 제거된 임시 DB에 속했다.

## 9. 배포 전에 반드시 할 일

### 9.1 팀 검토와 Git

- [ ] 현재 브랜치와 전체 Diff를 확인한다. 새 파일과 삭제 파일을 모두 포함한다.
- [ ] 기준 develop-api 이후 추가 변경이 있는지 다시 fetch해 확인한다.
- [ ] 팀원 새 코드와의 충돌이 있으면 기능별로 병합하고 회귀 테스트를 다시 수행한다.
- [ ] 재수집 파일 처리, 증분 ORM 제거, 오류 기록 변경은 Backend 담당이 검토한다.
- [ ] 인계받은 원격 복원 브랜치에서 작업을 이어가고, 추가 수정 후 회귀 테스트를 수행한다.
- [ ] develop-api 반영 여부와 방법은 팀 검토 후 별도로 결정한다. 이번 인계에서는 PR을 만들지 않는다.

복원 작업 커밋 메시지:

```text
refactor: restore full collection structure and preserve retry safeguards
```

현재 보존용 backup 커밋과 복원 브랜치의 커밋을 혼동하지 않는다. 강제 push, reset --hard,
DB downgrade는 배포 절차에 포함하지 않는다.

인계 대상 저장소는 `https://github.com/growingondev/one-cycle`이며, 별도 브랜치
`fix/restore-full-collection`을 사용한다. 원격 게시 성공 여부와 최종 커밋 ID는
작업자의 푸시 완료 안내 및 아래 원격 조회로 확인한다.

팀원은 기존 미커밋 작업을 먼저 보존하고 다음 명령으로 브랜치를 가져온다.
같은 이름의 로컬 브랜치가 아직 없을 때 사용하는 명령이다.

```bash
git fetch origin
git switch -c fix/restore-full-collection --track origin/fix/restore-full-collection
git log -1 --oneline
git status --short
```

이미 로컬 브랜치가 있다면 새로 생성하지 말고 해당 브랜치의 상태와 원격 차이를 먼저 확인한다.
보존용 `backup/frontend` 브랜치를 별도로 가져올 필요는 없다. 복원 코드·테스트·인수인계 문서는
복원 브랜치에 함께 포함한다. 이번 인계는 운영 배포나 develop-api 병합을 의미하지 않는다.

### 9.2 기존 활성 Run의 비노출 공고 확인

이번 코드는 is_visible 필터를 제거한다. 기존 활성 Run에 증분 방식으로 숨겨 놓은 공고가
있으면 첫 정상 전체 Run으로 전환하기 전에 해당 공고가 다시 보일 수 있다.

AWS DB에서 담당자가 수행할 읽기 전용 확인 예시:

```sql
SELECT s.active_collection_run_id, count(*) AS hidden_count
FROM system_state s
JOIN announcements a ON a.collection_run_id = s.active_collection_run_id
WHERE s.id = 1 AND a.is_visible IS FALSE
GROUP BY s.active_collection_run_id;
```

행이 없거나 hidden_count가 0이면 이 조건에 해당하는 공고는 없다는 뜻이다.
결과가 있으면 다음 중 팀이 합의한 전환 절차가 필요하다.

1. 기존 버전의 전체수집으로 정상적인 전체 Run을 Publish한 뒤, 증분 Scheduler가 다시
   추가하지 못하도록 중단·확인하고 새 버전을 배포한다.
2. 점검 시간에 새 버전을 적용하고 첫 정상 전체 Run을 Publish한 뒤 서비스를 재개한다.

수집·재시도 진행 여부와 Scheduler 정지 시점을 함께 조율한다. 이 문서만 보고 현재
실행 중인 컨테이너를 즉시 중단하거나 DB 값을 일괄 수정하지 않는다.

### 9.3 배포와 운영 검증

명령 실행 위치: **AWS 서버의 저장소 루트**. 팀 PR 병합, 서버 코드 갱신, 전환 순서 승인 후
사용할 예시이며 이번 로컬 작업에서 실행한 AWS 명령이 아니다.

```bash
docker compose -f infra/docker-compose.yml build crawler backend
docker compose -f infra/docker-compose.yml up -d --no-deps crawler backend scheduler
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs --tail=100 crawler backend scheduler
```

Backend와 Scheduler는 동일 이미지다. 이번 변경 자체에는 새 마이그레이션이 없으며,
기존 Worker/RAG/Frontend가 필요한 최신 버전이라는 전제에서 해당 이미지 재빌드는 불필요하다.

운영 검증 체크리스트:

- [ ] `COLLECTION_RUNNER`가 `collect_persist_and_process`를 가리킨다.
- [ ] Crawler/Backend/Scheduler/Worker의 공유 원본 접근과 쓰기 권한이 맞다.
- [ ] 기존 체크섬 경로의 문서 다운로드와 재처리가 된다.
- [ ] 신규 원본은 실행별 경로에 남고 `_temp_download`만 정리된다.
- [ ] 실제 LH 첫 페이지 전체수집이 완료되고 총/성공/실패 건수를 확인했다.
- [ ] primary 문서가 실제 Worker·임베딩 서비스를 통과했다.
- [ ] Publish 전에는 이전 Run, 성공 후에는 새 Run이 공고 목록과 RAG에 적용된다.
- [ ] 실패 시 기존 활성 Run이 유지된다. 장애 주입은 별도 테스트 데이터에서 한다.
- [ ] 관리자 대상 파일 재시도와 단계별 재시도가 정상 동작한다.
- [ ] 실제 처리 시간과 API/프록시/Worker timeout이 충돌하지 않는다.
- [ ] 예약 시각 로그가 맞고 중복 실행이 건너뛰어졌을 때 대응 방법이 정해져 있다.

이 체크리스트가 끝나기 전에는 ‘AWS 운영 검증 완료’라고 표시하지 않는다.

## 10. 2단계: Run 보관·삭제·롤백 계획 (미구현)

### 10.1 합의된 목표와 아직 필요한 결정

목표는 현재 활성 Run과 직전 정상 Run 1개를 유지하고 더 오래된 데이터를 정리하는 것이다.
단, 다음 세부 기준은 구현 전에 Backend/DB·Crawler·문서 처리·RAG 담당이 합의해야 한다.

| 결정 항목 | 확인할 내용 |
| --- | --- |
| ‘직전 정상’ 기준 | 실제 Publish 성공 이력 기준인지, 롤백 후 previous 포인터를 어떻게 바꿀지 |
| 실패/미공개 Run | 즉시 정리, 기간 보관, 수동 확인 중 무엇인지 |
| 실행 중 Run | Crawler/문서 재시도/평가에서 사용 중인 Run을 어떻게 보호할지 |
| 삭제 범위 | DB 원본·파생 테이블·다운로드·Worker 산출물·오류/감사 로그 각각의 보관 기준 |
| 삭제 시점 | Publish 직후 별도 작업인지, 유예 시간 후인지 |
| 롤백 권한 | 누가 실행하고 무엇을 확인하며 이력을 어디에 남길지 |
| 외부 참조 | 채팅 근거·평가 데이터·기존 문서 링크가 삭제 대상 ID를 참조하면 어떻게 할지 |

주의: `CollectionRun.status='success'`는 수집 결과의 상태다. 이후 분석이나 Publish가
실패했을 수도 있으므로 이 컬럼만으로 ‘직전 정상 서비스 Run’을 고르면 안 된다.
현재 상태 모델의 active 포인터만으로 충분한 Publish 이력이 보존된다고 가정하지 않는다.

### 10.2 권장 구현 순서 — 설계 제안

아래는 후속 담당자가 검토할 제안이며 현재 코드에 존재하는 기능이 아니다.

1. **Publish 이력과 보호 대상 기록**
   - active/previous 또는 별도 Publish 이력 테이블 중 팀 구조에 맞는 방식을 선택한다.
   - 성공한 공개 전환과 직전 Run 갱신을 같은 DB 트랜잭션에서 처리한다.
   - 신규 마이그레이션으로 적용하고 기존 이력의 초기값을 검증한다.
2. **삭제 대상 미리보기**
   - 보호 대상, 실행 중 작업, 유지 참조를 제외한 Run과 파일 목록을 산출한다.
   - 먼저 dry-run 보고서만 만들어 건수·경로·예상 용량을 검토한다.
3. **재실행 가능한 정리 작업**
   - DB와 파일시스템 삭제는 하나의 원자적 트랜잭션이 아니므로 단계별 상태와 재시도 기준을 둔다.
   - 예를 들어 삭제 계획을 기록하고 비활성화/파일 정리/DB 정리의 순서를 설계한다.
   - 프로세스가 중간에 종료돼도 active/previous 데이터를 지우지 않아야 한다.
4. **롤백 기능**
   - 보존된 Run의 DB·원본·청크·임베딩이 여전히 유효한지 검증한다.
   - 공개 포인터 전환과 이력 기록을 함께 처리하고 RAG·목록을 확인한다.
   - 삭제 작업과 롤백이 동시에 실행될 때 보호 대상이 바뀌는 경합을 차단한다.
5. **운영 적용**
   - 테스트 DB/임시 파일 → 별도 통합 환경 → 팀 승인 후 AWS 순서로 적용한다.
   - 초기에는 실제 삭제 대신 후보 로그만 확인하는 기간을 둘지 결정한다.

### 10.3 파일 정리에서 특히 주의할 점

- CollectionRun과 디스크 실행 폴더는 항상 1:1이 아니다. 개별 재수집 원본은 별도
  recollect 폴더에 있으면서 기존 Run의 Document가 참조한다.
- 같은 파일을 재사용한 Document나 기존 체크섬 버전 경로가 여러 곳에서 참조될 수 있다.
- Worker 산출물 경로는 원본 경로와 다르며 별도 참조 확인이 필요하다.
- 따라서 파일 생성 시각, 폴더 이름, ‘최근 폴더 2개’만으로 삭제 대상을 정하면 안 된다.
- 지원 루트 안의 확정된 개별 경로만 처리하고 심볼릭 링크/경로 이탈을 다시 검사한다.
- DB FK cascade, RESTRICT, ErrorLog/채팅/평가 참조를 실제 마이그레이션 기준으로 조사한다.
- 새 파일 중복 제거 코드가 있으므로 전체 Run 보관·삭제도 해결됐다고 판단하면 안 된다.

### 10.4 후속 작업에서 우선 볼 파일

- `backend/app/services/collection_publish_service.py`: 공개 전환 경계.
- `backend/app/models/system_state.py`, `collection_run.py`: 현재 상태·수집 회차 모델.
- `backend/app/models/`: Document, ProcessingRun, ChunkSet, Chunk, Embedding 및 참조 관계.
- `backend/app/services/collection_service.py`: 재수집과 기존 Document 재사용.
- `backend/app/services/pipeline_persistence.py`, `document_worker/service.py`: 산출물 경로와 활성 처리 결과.
- `backend/app/services/error_retry_service.py`: 실행 중 개별 재시도와 정리의 경합.
- `rag/db_pipeline.py`, `rag/retrieval/keyword_search.py`: active Run 기준 검색.
- `migrations/versions/`: 적용된 스키마 확인 및 후속 신규 마이그레이션.

### 10.5 2단계 필수 테스트 제안

- A → B → C를 정상 Publish하면 C와 B를 보존하고 A만 정리 후보가 된다.
- C 처리/Publish 실패 시 active B, previous A를 유지한다.
- current/previous/실행 중 Run과 연결 파일은 삭제할 수 없다.
- C → B 롤백 전후 공고 목록·벡터·BM25 검색이 함께 전환된다.
- 롤백 직후 다음 Publish에서 previous가 올바르게 갱신된다.
- 다른 보호 Run이 참조하는 파일은 삭제하지 않는다.
- 개별 재수집으로 경로가 복구되는 동안 정리 작업이 해당 파일을 지우지 않는다.
- DB 오류, 파일 삭제 권한 오류, 중간 종료 후 재실행에도 상태를 복구할 수 있다.
- 같은 정리 요청을 두 번 실행해도 추가 데이터가 손상되지 않는다.
- 실패/미공개 Run 및 고아 파일에 대해 합의한 보관 정책이 적용된다.

## 11. 담당별 인수인계와 완료 기준

| 담당 | 다음 확인/작업 |
| --- | --- |
| Crawler | 실제 LH 목록·첨부 변경 대응, 실행별 저장·임시 정리, 전체/개별 다운로드 검증 |
| Backend/DB | 재수집 DB·파일 처리와 오류 연결 리뷰, 전환 순서, 보관/삭제/이력·롤백 설계 |
| 문서 처리 | 실제 단계별·자동 재시도, 복구 원본 재처리, 기존 추출 테스트 실패 4개 확인 |
| RAG | 운영 DB에서 active Run 검색과 근거 링크 검증, 향후 롤백·참조 삭제 영향 확인 |
| 배포 담당 | 진행 작업 확인, 비노출 데이터 점검, 공유 볼륨/설정, PR 반영·이미지 교체·운영 종단 검증 |

우선순위:

1. 팀 코드 리뷰와 배포 전환 방식 확정.
2. 인계 브랜치에서 최신 develop-api와의 차이 재확인 및 회귀 테스트. PR·병합은 팀이 별도 결정.
3. 실제 AWS 종단 검증으로 1단계 운영 적용 완료 확인.
4. 기존 추출 실패·timeout·정리 오류 관측 등 확인된 잔여 항목 분류.
5. 2단계 세부 정책 합의 → 삭제 후보 dry-run → 보관·롤백 → 실제 정리 순서로 진행.

### 다음 작업자에게 전달할 요약

> 최신 develop-api 기반 복원 브랜치에서 증분 코드를 실제 제거하고, 31d7b38의 Crawler
> 전체수집·실행별 저장 구조를 복원했습니다. Backend·DB는 153a814를 참고했고, 최신
> 단계별/자동 재시도와 Scheduler·공통 잠금·409를 유지했습니다. 재수집 중복 파일 정리와
> 누락 원본 복구, 전체수집 오류의 대상 파일 연결을 추가했습니다. 테스트는 210개 통과,
> 기존 추출 오류 4개가 남습니다. 실제 DB 잠금·Publish·RAG 및 Docker 기동은 검증했으나
> AWS의 실제 LH→Worker→임베딩 전체 흐름은 아직입니다. 운영 DB/파일은 변경하지 않았고,
> 복원본은 fix/restore-full-collection 브랜치로 인계하며 이번에는 PR을 만들지 않습니다. 배포 전에 기존 active Run의 비노출 데이터와
> 공유 경로를 확인해야 합니다. Run 2개 보관·오래된 데이터 삭제·운영 롤백은 미구현이며,
> 이 문서 10장의 정책을 합의한 뒤 별도 단계로 진행해야 합니다.


## 12. AWS 실제 종단 검증 결과 (2026-09-04)

이 절은 앞선 “AWS 미실시” 상태를 실제 운영 환경 검증 결과로 갱신한다.
앞선 기록과 상충하는 경우 이 절의 상태가 최신이다.

### 12.1 검증 환경과 적용 상태

| 항목 | 결과 |
| --- | --- |
| AWS 검증 브랜치/커밋 | `fix/restore-full-collection` / `92310f4` |
| DB 마이그레이션 | 기존 `8f4d1c2a7b90` 유지, 신규 적용 없음 |
| 배포 | Backend·Crawler 이미지 재빌드 및 컨테이너 재생성 |
| 증분 API 제거 | Crawler Scan 제거, 관리자 Sync 제거 확인 |
| 서비스 상태 | Backend·DB·Crawler Health 정상 |
| 검증 전 활성 데이터 | Run 9, 사용자 공고 64건 |
| 검증 후 활성 데이터 | Run 10, 사용자 공고 50건 |

평가 관련 AWS 로컬 변경은 Git stash와 별도 패치로 보존한 뒤 검증했으며,
이번 브랜치의 코드·DB 마이그레이션과 섞지 않았다.

### 12.2 관리자 수동 전체수집 E2E

관리자 페이지에서 전체수집을 한 번 실행해 다음 결과를 확인했다.

- Crawler job ID: `execution_20260904_181153_1118fb`
- Crawler execution ID: `execution_20260904_181153_1a7909a4dea5`
- LH 목록 1페이지 공고: 50건
- 성공/실패: 50/0
- Crawler errors: 0
- 새 CollectionRun: Run 10
- 처리 대상 primary 문서: 46건
- 문서 처리 결과: 46건 성공, 대기 0건, 실패 0건
- 처리 중에는 기존 Run 9를 유지하고, 전체 처리 완료 후 Run 10으로 활성 전환
- 사용자 공고 API: Run 10 기준 총 50건 반환

따라서 실제 LH 수집부터 DB 저장, Worker 처리, 청킹·임베딩, Publish,
사용자 조회까지의 정상 성공 경로가 AWS에서 완료됐다.

### 12.3 파일 저장과 정리

실행 폴더:
`/home/ubuntu/ddokbot/data/documents/execution_20260904_181153_1a7909a4dea5`

- 공고별 디렉터리 50개 생성
- 첨부파일 79개 보존
- 저장 구조: `{execution_id}/{source_announcement_id}/{filename}`
- 실행 종료 후 `_temp_download` 제거 확인
- 새 체크섬 버전 저장 구조를 만들지 않음

### 12.4 유지 기능 회귀 검증

| 기능 | AWS 검증 결과 |
| --- | --- |
| 개별 공고 재수집 | 공고 379 재수집 성공 |
| 기존 문서 재사용 | Document 635 유지, 중복 Document 미생성 |
| 재수집 후 데이터셋 | active CollectionRun 10 유지 |
| 관리자 문서 재처리 | Document 635 재처리 성공 |
| 처리 결과 교체 | ProcessingRun 446 비활성, 492 활성 |
| 자동 재시도 | 임시 Backend 컨테이너에서 관련 단위 테스트 10개 통과 |
| 사용자 문서 다운로드 | 사용자 화면에서 정상 확인 |
| 사용자 챗봇 | Run 10 공고에서 응답·근거 연결 정상 확인 |
| Scheduler | 컨테이너 정상 기동, Asia/Seoul 12·15·18시 예약 등록 |

자동 재시도 테스트는 모의 실패를 사용했으며 운영 DB와 실제 문서를 변경하지 않았다.
사용자 챗봇 검증은 새 활성 데이터와 RAG 연결 확인이며 답변 정확도 평가를 의미하지 않는다.
Scheduler는 예약 등록까지 확인했고 실제 예약 시각의 자동 전체수집은 후속 확인 대상이다.

### 12.5 아직 구현하거나 확인하지 않은 범위

- 관리자 공고 목록을 활성 Run만 표시할지, 보관 Run까지 표시할지에 대한 조회 정책
- 실제 예약 시각에 Scheduler가 시작한 전체수집의 완료 확인
- AWS 운영 데이터에 장애를 강제로 주입한 실패·동시 실행 검증
- 기존 핵심정보 추출 테스트 실패 4건 수정

Run 보관·삭제 구현과 배포 절차는 `COLLECTION_RUN_RETENTION.md`를 기준으로 한다.
관리자 API 조회 범위는 별도 정책이므로 보관 Run 공고가 함께 보일 수 있다.

### 12.6 보관·삭제 정책과 롤백 범위 정정

현재 팀에서 확정한 다음 단계는 아래까지다.

1. 새 Run의 수집·문서 처리·검증이 모두 성공한 경우에만 활성화한다.
2. 새 활성 Run과 직전 정상 Run 1개를 보관한다.
3. 그보다 오래된 Run의 DB 데이터와 실제 파일을 안전하게 정리한다.
4. 새 Run이 실패하면 활성 전환과 오래된 데이터 정리를 수행하지 않는다.
5. 관리자 직접 삭제 버튼은 이번 MVP 범위에서 제외한다.

관리자가 실행하는 롤백 버튼/API는 구현하기로 확정한 기능이 아니다.
직전 정상 Run 보관은 복구 가능성을 남기는 데이터 정책이며, 자동 또는 관리자 롤백 기능의
구현 약속을 의미하지 않는다. 본 문서 10장의 롤백 관련 내용은 설계 검토 제안으로만 읽으며,
현재 필수 구현 범위에는 포함하지 않는다.

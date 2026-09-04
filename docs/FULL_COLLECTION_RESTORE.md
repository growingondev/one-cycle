# 전체수집 구조 복원 — 1단계

파일별 구현 내역, 검증 범위, 운영상 남은 제약과 2단계 계획은
`docs/FULL_COLLECTION_HANDOFF_20260904.md`에 상세히 기록했다.

## 작업 기준

- 작업 브랜치: `fix/restore-full-collection`, 기준 `origin/develop-api`의 `4df342a`
- 기존 중간 수정본 보존: `backup/frontend`의 `5d47338`
- Backend HTTP/DB 저장/Publish 참고: `153a814`
- Crawler 복원 원본: 목록 DOM 복원 수정이 포함된 `31d7b38`
- 두 기준 사이 Backend·DB 변경이 없음을 Git으로 확인했다.
- 과거 브랜치 전체 병합, develop-api 강제 변경, 운영 DB downgrade는 하지 않았다.

## 운영 흐름

```text
Scheduler (Asia/Seoul 12·15·18시) / 관리자 전체수집
→ collect_announcements() [공통 PostgreSQL 잠금]
→ COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
→ Crawler POST /v1/crawl-jobs
→ 새 CollectionRun / Announcement / Document
→ primary 문서 처리·청킹·임베딩 (단계별·자동 재시도 유지)
→ 기존 Publish 검증 → 성공 시 활성 Run 전환
```

- 기존 범위인 **LH 목록 1페이지 전체**다. 모든 페이지 순회는 아니다.
- 변경 여부로 생략하지 않으며 동일 공고도 새 회차 문서로 처리한다.
- 지원 HWP/HWPX의 다운로드 결과를 Document로 기록한다.
- 다운로드 완료된 `primary`만 분석하고 `supporting`은 분석하지 않는다.
- 분석 대상이 없는 공고는 기존 metadata-only Publish 정책을 유지한다.
- 부분 수집·빈 결과·처리 실패·임베딩 누락이면 기존 활성 Run을 유지한다.
- `collection_publish_service.py`와 분석 대상 선정 기준은 변경하지 않았다.
- 보관·삭제·새 롤백 기능은 2단계이며 이번에 구현하지 않았다.

## 제거 / 유지

증분 서비스·Gateway·관리자 Sync Route, Scan 작업 생성/실행·Client·목록 전용 스캔,
메타데이터 비교·정정 연결·선택 수집, 증분 전용 테스트·운영 문서를 실제 제거했다.
공고 조회의 `a.is_visible IS TRUE` 조건 3곳과 증분 ORM 매핑도 제거했다.
`DOCUMENT_STORAGE_ROOT` 설정, `current.json` 갱신 및 신규 체크섬 버전 저장을 제거했다.

다음 공통 API는 유지한다.

- `POST /v1/crawl-jobs`
- `GET /v1/crawl-jobs/{job_id}`
- `GET /v1/crawl-jobs/{job_id}/result`
- `POST /v1/recollect-jobs`
- 관리자 전체수집·개별 재수집·오류 재시도, 문서 다운로드

관리자 Sync Route는 OpenAPI에서도 제거했다. 기존 GET `/announcements/{announcement_id}`
때문에 Sync 주소에 POST하면 프레임워크가 404 대신 **405**를 반환할 수 있다.
410 대체 Route를 남기지는 않았다. Crawler Scan POST는 404다.

`pipeline_persistence.py`의 Chunk metadata `normalized_title`은 증분 공고 필드가 아닌
기존 문서 구조 정보이므로 유지했다. 지역·다운로드·Worker·Frontend·RAG 기능은 유지한다.

## 실행별 저장 및 재수집

```text
CRAWLER_STAGING_DIR/
  execution_<timestamp>_<unique>/공고ID/파일명
  recollect_<timestamp>_<unique>/공고ID/파일명
```

실행 ID 충돌과 원격 ID/파일명의 경로 이탈을 방지한다. 실행 종료 시 해당 실행의
`_temp_download`만 정리하고 다운로드 원본은 남긴다.

| 개별 재수집 상황 | 처리 |
| --- | --- |
| 동일 체크섬, 기존 파일 존재·내용 일치 | 기존 Document 유지, 새 중복 파일만 삭제 |
| 동일 체크섬, 기존 파일 누락/손상 | 기존 Document 경로 복구, primary 재처리 |
| 다른 체크섬 | 새 Document 생성, primary 처리 |
| 다른 공고의 같은 파일명 | 별도 공고 디렉터리·Document 사용 |

중복 삭제는 DB 저장 성공 후 수행한다. 현재 실행/공고/파일 경로, 실제 체크섬,
기존 파일 존재 및 다른 Document 참조를 재확인한다. 다른 실행·공고·기존 원본이나
경로 이탈·심볼릭 링크 대상은 삭제하지 않는다. 정리 실패는 로그와
`duplicate_cleanup_errors`로 반환한다.

기존 `notices/.../versions/...` 파일은 DB 기록 경로로 계속 읽는다. 이동·삭제하지 않는다.
전체수집 다운로드 오류도 ErrorLog에 공고·문서·`target_filename`과 연결해 관리자
다운로드 재시도에 필요한 정보를 남긴다.

## 설정과 DB 호환성

- Crawler·Backend·Scheduler는 같은 `CRAWLER_STAGING_DIR`와 공유 볼륨을 사용한다.
- Compose는 세 서비스에 `/data/documents`를 주입한다.
- 로컬 네이티브 실행에서는 Crawler에도 동일한 환경변수를 전달해야 한다.
  Crawler가 Backend처럼 `.env`를 자동으로 읽는다고 가정하지 않는다.
- `c4b2e71a9d10`, `8f4d1c2a7b90` 마이그레이션 파일은 변경하지 않았다.
- 기존 DB 컬럼은 물리적으로 남고 기본값을 사용한다. 증분 ORM 매핑은 제거했으므로
  **autogenerate가 제안하는 컬럼 DROP을 그대로 적용하면 안 된다.** 컬럼 정리는
  담당자 합의 후 별도 신규 마이그레이션으로 처리한다.

## 배포 전에 확인할 사항

AWS 배포와 실제 LH 전체수집은 이 로컬 작업에서 실행하지 않았다.

기존 활성 Run이 증분 방식으로 누적된 상태이면 비노출 공고를 포함할 수 있다.
이번 변경은 `is_visible` 필터를 제거하므로 **첫 정상 전체 Run을 Publish하기 전에
구 활성 Run을 그대로 서비스하면 비노출 공고가 다시 노출될 수 있다.** 배포 전에 확인한다.

```sql
SELECT count(*) AS hidden_in_active_run
FROM announcements a JOIN system_state s ON s.active_collection_run_id = a.collection_run_id
WHERE s.id = 1 AND a.is_visible IS FALSE;
```

0이 아니면 구버전 관리자 전체수집으로 정상 전체 Run을 먼저 Publish하고 증분 Scheduler를
중단한 상태에서 배포하거나, 점검 시간에 신규 전체 Run Publish 후 서비스를 재개한다.
기존 데이터 삭제·컬럼값 일괄 변경으로 우회하지 않는다. 진행 중인 재시도도 완료를 확인한다.

팀 검토·PR 반영 후 AWS 저장소 루트에서 적용할 명령 예시:

```bash
docker compose -f infra/docker-compose.yml build crawler backend
docker compose -f infra/docker-compose.yml up -d --no-deps crawler backend scheduler
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs --tail=100 crawler backend scheduler
```

Backend/Scheduler는 동일 이미지를 사용한다. 이번 변경 자체에 새 마이그레이션은 없다.
Worker·RAG·Frontend는 이번 변경으로 재빌드할 필요가 없다. 기존 최신 버전이 실행 중이라는
전제이며, 실제 공유 볼륨·Worker·임베딩 연결과 전체수집 1회 성공을 운영 환경에서 확인한다.

## 테스트

```bash
python -B -m pytest tests -q -p no:cacheprovider
```

실제 DB 테스트는 `ONE_CYCLE_TEST_POSTGRES_URL`에 별도 loopback PostgreSQL을 지정한다.
DB 이름이 `restore_test`로 시작하지 않으면 거부한다. 기존
`infra/postgres/init/01-enable-vector.sql`로 vector 확장을 활성화하고 기존 마이그레이션을
head까지 적용한다. 운영 DB URL을 사용하지 않는다.

- PostgreSQL 잠금: 관리자 ASGI와 Scheduler를 별도 프로세스에서 동시 실행한다.
  양방향 차단·409·성공/실패/예외 후 재획득, 수집→처리→Publish 동안 동일 세션 잠금,
  장시간 idle transaction이 없음을 확인한다.
- PostgreSQL Publish: 실제 스키마·pgvector에서 전환 전후 공고·벡터·BM25 검색 범위와
  임베딩 누락 시 기존 Run 유지를 확인한다. 기존 Publish 함수를 이용한 역방향 전환도
  검증하지만 새 롤백 기능을 구현한 것은 아니다.
- 재수집: 실제 임시 파일+격리 DB로 중복 삭제·누락 복구·변경 파일·경로 안전·
  DB 실패 시 파일 보존·전체수집 오류 연결을 검사한다.
- Crawler: Selenium 응답을 대체해 첫 페이지 전수 순회·DOM 복원 대기·실행별 파일 보존·
  임시 폴더만 정리를 검사한다.
- 기존 다운로드·지역·단계별/자동 재시도·API 테스트도 함께 실행한다.

실제 DB 테스트에서도 LH·Worker·질문 임베딩은 모의/합성 데이터다.
AWS에서 실제 LH 다운로드부터 AI 처리까지 검증하는 운영 종단 테스트를 대신하지 않는다.

### 이번 실행 결과 (2026-09-04)

- 실제 PostgreSQL 옵션을 켠 전체 테스트: **210 passed / 4 failed**, 15 subtests passed.
- 실패 4개는 수정 전부터 존재한 신청기간 시간 추출 3개와 공급정보 요약 1개다.
  수집 구조 복원 범위 밖이므로 구현이나 기대값을 바꾸지 않았다.
- PostgreSQL 프로세스 간 잠금 6개와 Publish·RAG DB 통합 2개 모두 통과했다.
- 별도 테스트 DB에서 기존 초기화 SQL + 마이그레이션으로 `8f4d1c2a7b90 (head)` 확인.
- Backend/Scheduler 및 Crawler 별도 Docker 테스트 이미지 빌드 통과.
- 테스트 컨테이너의 Backend DB health / Crawler health HTTP 응답 정상.
- 변경 Python 파일의 치명적 문법/이름 검사와 `git diff --check` 통과.
- 실제 LH·Worker·임베딩 모델을 모두 연결한 AWS 종단 검증은 미실시.
- 원래 실행 중이던 다른 Docker 컨테이너는 변경하지 않았다. 이번 임시 테스트 컨테이너는
  검증 후 종료·자동 제거했고, 재검증용 `onecycle-restore-backend:test`, `onecycle-restore-crawler:test`
  이미지는 로컬에 남긴다.

복원 코드·테스트·문서는 `fix/restore-full-collection` 브랜치로 인계한다.
이번 인계에서는 PR을 만들거나 develop-api를 변경하지 않는다. 게시 결과와 최종 커밋 ID는
푸시 완료 안내에서 확인하며, 팀원이 브랜치를 가져오는 절차는 상세 인수인계 문서 9.1절을 참고한다.
복원 작업 커밋 메시지:

```text
refactor: restore full collection structure and preserve retry safeguards
```

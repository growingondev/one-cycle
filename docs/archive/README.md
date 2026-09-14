# 개발 과정 기록

이 폴더에는 DDOKBOT을 개발하면서 작성한 마이그레이션, 통합, 장애 해결, 실행 검증 기록을 보관합니다.

이 문서들은 당시의 코드와 운영 환경을 기준으로 작성되어 현재 동작과 다를 수 있습니다. 현재 시스템을 이해할 때는 먼저 상위 `docs/README.md`에 정리된 현재 기준 문서를 확인합니다.

## API·서비스 분리 기록

- `API_MIGRATION_HISTORY.md`
- `BACKEND_CRAWLER_HTTP_INTEGRATION_20260902.md`
- `BACKEND_DB_INTEGRATION_HISTORY.md`

## 검증·오류 수정 기록

- `BACKEND_DB_RUNTIME_VALIDATION_20260826.md`
- `BACKEND_DOCUMENT_PROCESSING_AUTO_RETRY_20260904.md`
- `BACKEND_E2E_HOTFIX_VALIDATION_20260902.md`
- `DOCUMENT_ROLE_CLASSIFICATION_FIX_20260907.md`

## 전체수집 복원 기록

- `FULL_COLLECTION_HANDOFF_20260904.md`
- `FULL_COLLECTION_RESTORE.md`

## 주의사항

- 과거 경로, Commit, 환경변수 예시는 현재 운영값으로 간주하지 않습니다.
- 현재 동작은 실제 코드, `.env.example`, `infra/docker-compose.yml`과 상위 기준 문서를 우선합니다.
- 비밀번호, SSH Key, 실제 `.env` 값은 이 폴더에도 기록하지 않습니다.

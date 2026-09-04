# Backend 문서 처리 자동 재시도 기록

## 작업 범위

- 작업 브랜치: `feat/document-processing-auto-retry`
- 기준 커밋: `12d1aff`
- 구현 커밋: `853bb43`
- 목적: 문서 처리의 일시적인 실패가 전체 수집 실패로 바로 확정되지 않도록 Backend에서 자동 재시도

## 기존 상태

- `process_document_ids()`는 문서마다 `reprocess_document()`를 한 번만 호출했다.
- 문서 처리 결과가 실패이거나 호출 중 예외가 발생하면 즉시 `ErrorLog`를 생성했다.
- 분석 대상 문서가 하나라도 실패하면 해당 수집 결과는 Publish하지 않았다.
- 실패 단계부터 다시 처리하는 Worker 및 관리자 수동 재시도 기능은 기존에 구현돼 있었다.

## 변경 내용

- 최초 처리를 포함해 문서별 최대 3회 시도한다.
- Worker가 실패 단계 정보를 반환하면 다음 시도는 해당 단계부터 시작한다.
- 단계 정보가 없는 예외나 잘못된 반환값은 문서 처리 처음부터 다시 시도한다.
- 시도 사이에는 기본 5초를 기다린다.
- 중간 실패는 Backend 로그에만 기록한다.
- 재시도 중 성공하면 해당 문서를 정상 처리된 것으로 계산한다.
- 3회 모두 실패한 경우에만 최종 실패 결과로 `ErrorLog`를 한 번 생성한다.
- `PipelineUnavailableError`처럼 서비스 설정이나 실행 경로가 준비되지 않은 오류는 자동 재시도하지 않고 즉시 전달한다.
- 최종 실패 문서가 있으면 기존과 동일하게 새 수집 결과를 Publish하지 않는다.

## 처리 흐름

```text
문서 처리 1차 시도
  → 성공: 다음 문서 처리
  → 실패 단계 확인
      → 단계 있음: 해당 단계부터 재시도
      → 단계 없음: 처음부터 재시도
  → 최대 3회 안에 성공: 정상 처리
  → 3회 모두 실패: ErrorLog 생성 및 Publish 중단
```

## 환경설정

```env
DOCUMENT_PROCESSING_MAX_ATTEMPTS=3
DOCUMENT_PROCESSING_RETRY_DELAY_SECONDS=5
```

- `DOCUMENT_PROCESSING_MAX_ATTEMPTS`는 최초 시도를 포함한 전체 시도 횟수다.
- 설정하지 않으면 각각 `3회`, `5초`를 기본값으로 사용한다.
- 자동 재시도를 끄려면 최대 시도 횟수를 `1`로 설정한다.

## 변경 파일

- `.env.example`
  - 자동 재시도 횟수와 대기시간 예시 추가
- `backend/app/core/config.py`
  - 자동 재시도 설정 추가
- `backend/app/services/integration_service.py`
  - 재시도 실행, 실패 단계 전달, 중간 로그 및 최종 오류 기록 구현
- `tests/backend/test_integration_service.py`
  - 실패 단계 재시도, 최종 실패, 단계 없는 예외 재시도 검증

## 로컬 검증 결과

- 자동 재시도 관련 테스트: 19/19 통과
- Backend 전체 테스트: 161개 중 157개 통과
- Ruff 검사: 통과
- Python 전체 컴파일: 통과
- `git diff --check`: 통과
- 기존 실패 4개
  - 신청 기간에서 시간 정보가 빠지는 Key Information Extractor 테스트 3개
  - 공급정보 요약이 비어 있는 Key Information Extractor 테스트 1개
- 기존 실패 4개는 이번 자동 재시도 변경과 직접 관련이 없다.

## 담당 범위 구분

- Document Worker: 각 처리 단계 실행 및 실패 단계부터 재개
- Backend: 재시도 횟수·간격 결정, 재시도 호출, 최종 실패 기록, Publish 여부 결정
- 이번 작업은 기존 Worker의 단계별 재시도 기능을 Backend 전체 수집 흐름에 자동으로 연결한 작업이다.

## 남은 검증 및 제한사항

- GitHub 병합 후 AWS에서 실제 Backend·Document Worker HTTP 환경으로 검증해야 한다.
- 현재 재시도는 같은 Backend 실행 흐름 안에서 동기적으로 수행된다.
- Backend나 Worker 컨테이너가 재시작되면 진행 중이던 재시도 상태는 복원되지 않는다.
- 별도의 영속 작업 큐나 일정 시간이 지난 뒤 다시 실행하는 예약 재시도는 이번 범위에 포함하지 않았다.
- 이전 활성 데이터 자동 삭제 정책은 별도 후속 작업으로 구현한다.

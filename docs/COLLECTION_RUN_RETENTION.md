# CollectionRun 보관·삭제 운영

## 확정 범위

- 새 전체수집 Run의 수집·문서 처리·검증이 모두 성공한 뒤 Publish한다.
- Publish된 활성 Run과 그 직전에 서비스하던 Run 1개를 보관한다.
- 그 외 오래된 Run의 DB 데이터, 원본 문서, 문서 처리 결과를 자동 정리한다.
- 새 Run이 실패하면 활성 Run을 바꾸지 않고 정리도 실행하지 않는다.
- `running` 상태 Run은 정리 대상에서 제외한다.
- 관리자 수동 삭제와 롤백 UI/API는 이번 범위에서 제외한다.

## 데이터 기준

`system_state`가 두 포인터를 보관한다.

- `active_collection_run_id`: 현재 사용자 조회와 RAG가 사용하는 Run
- `previous_collection_run_id`: 활성화 직전에 서비스하던 Run

Publish 트랜잭션에서 기존 active 값을 previous에 기록한 뒤 새 Run을 active로
전환한다. 따라서 단순히 ID가 크거나 `status=success`인 Run을 직전 서비스
데이터라고 추측하지 않는다.

마이그레이션 직후 `previous_collection_run_id`는 의도적으로 `NULL`이다. 기존
운영 이력만으로 직전 Publish Run을 안전하게 확정할 수 없기 때문이다. 다음 정상
Publish가 두 포인터를 확정하기 전까지 정리 서비스는 아무것도 삭제하지 않는다.

## 실행 모드

`.env`의 `COLLECTION_RETENTION_MODE`를 사용한다.

| 값 | 동작 |
|---|---|
| `disabled` | Publish만 수행하고 보관·삭제 기능은 실행하지 않음 |
| `dry_run` | 삭제 후보와 파일 수만 계산하고 변경하지 않음 |
| `delete` | 보호 Run을 제외한 오래된 DB·파일을 실제 정리 |

처음 배포할 때는 반드시 `dry_run`으로 확인한 뒤 `delete`로 바꾼다.

## 삭제 순서와 실패 처리

1. `system_state` 행을 잠그고 active/previous를 다시 확인한다.
2. 두 보호 Run과 `running` Run을 제외한 후보를 계산한다.
3. 다른 보관 Run이 같은 경로를 참조하는 파일은 제외한다.
4. 허용된 문서·출력 루트 안의 경로만 삭제한다.
5. 파일 정리가 모두 성공한 경우에만 후보 CollectionRun을 DB에서 삭제한다.
6. FK `CASCADE`로 Announcement, Document, ProcessingRun, Chunk, Embedding 등
   하위 데이터를 정리한다. ErrorLog의 대상 FK는 기존 정책대로 `NULL`이 된다.

경로가 허용 루트 밖에 있거나 파일 삭제가 실패하면 DB Run을 남긴다. 이미
삭제된 비활성 파일은 다음 실행에서 missing으로 처리하고 나머지를 다시 정리할
수 있다. active/previous Run 파일은 어떤 경우에도 후보가 아니다.

## 배포 확인

```bash
alembic upgrade head
```

```sql
SELECT
  active_collection_run_id,
  previous_collection_run_id,
  updated_at
FROM system_state;
```

삭제 후보만 확인한다.

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  exec -T backend \
  python - <<'PY'
import json

from backend.app.services.collection_retention_service import (
    plan_collection_run_retention,
)

print(json.dumps(
    plan_collection_run_retention(),
    ensure_ascii=False,
    indent=2,
))
PY
```

`previous_collection_run_id`가 `NULL`이면 수동으로 값을 추측해 넣지 않는다.
다음 전체수집과 Publish를 먼저 완료한 뒤 다시 dry-run 결과를 확인한다.

실제 삭제는 `.env`를 `COLLECTION_RETENTION_MODE=delete`로 변경하고 Backend와
Scheduler를 재생성한 뒤, 다음 정상 Publish 직후 자동으로 실행한다.

## 결과 판정

- `completed`: 파일과 DB 정리 완료
- `dry_run`: 후보 계산만 완료
- `skipped`: active/previous 미확정 또는 삭제 후보 없음
- `file_cleanup_incomplete`: 파일 오류나 안전하지 않은 경로가 있어 DB 삭제 중단
- `failed`: 예외 발생. Publish는 이미 성공했으므로 새 활성 Run은 유지하고 오류 기록

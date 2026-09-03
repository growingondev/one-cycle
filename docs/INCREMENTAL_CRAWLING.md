# LH 공고 증분 수집 운영

## 실행 정책

- 최초 적재 또는 장애 복구: `POST /v1/crawl-jobs`
- 정기 변경 감지: 매일 `12:00`, `15:00`, `18:00` (Asia/Seoul)
- 관리자 수동 실행: `POST /api/admin/announcements/sync`
- 변경 공고 상세 수집: `POST /v1/recollect-jobs`

정기 실행은 LH 목록의 식별자와 메타데이터만 읽는다. 변경이 없는 공고는 상세
페이지 접속, 파일 다운로드, 파싱, 청킹, 임베딩을 모두 생략한다.

## 변경 판단

1. DB에 없는 `source_announcement_id`: 신규 공고
2. 신규 ID이면서 제목 말머리가 `[정정공고]`, `[수정공고]`, `[변경공고]` 등:
   정정 공고
3. 동일 ID의 메타데이터 SHA-256 변경: 수정 공고
4. 동일 ID와 동일 메타데이터 SHA-256: 변경 없음

정정 대상은 말머리를 제거한 제목을 기본으로 지역과 공고 유형을 함께 비교한다.
후보가 하나로 확정되지 않으면 기존 공고를 자동 비노출하지 않는다.

## 안전한 공개 전환

신규·정정 공고는 `is_visible=false`로 먼저 등록한다. 단건 수집과 문서 처리에
성공한 뒤에만 공개한다. 정정 공고의 처리가 성공한 경우에만 기존 공고를
비노출하며, 처리 실패 시 기존 정상 공고를 유지한다.

## 파일 저장

새 파일은 다음 구조에 저장한다.

```text
/data/documents/
├── staging/{execution_id}/
├── notices/{source_announcement_id}/
│   ├── versions/{checksum_sha256}/{filename}
│   └── current.json
└── runs/YYYY/MM/DD/{scan_execution_id}.json
```

기존 파일은 이동하지 않는다. Crawler, Backend, Scheduler, Document Worker는
동일한 `/data/documents` 볼륨을 공유한다.

## 배포

DB Migration을 서비스보다 먼저 적용한다.

```bash
alembic upgrade head
docker compose build crawler backend scheduler
docker compose up -d crawler backend scheduler
docker compose ps
docker compose logs --tail=200 crawler backend scheduler
```

Scheduler는 Backend와 같은 이미지를 사용하며 별도의 Dockerfile은 사용하지 않는다.

## 현재 MVP 제한

목록의 ID와 메타데이터가 그대로인 상태에서 LH가 동일 URL의 파일 내용만 교체하면
정기 목록 스캔만으로는 감지할 수 없다. 현재 운영 가정은 정정 파일이 새로운 ID와
정정 말머리로 게시되는 방식이다. 이 가정이 바뀌면 별도의 저빈도 파일 정합성 점검을
추가해야 한다.

# Document Worker API

## 1. 역할

Document Worker는 문서 처리 Pipeline을 HTTP 서비스로 감쌉니다. Backend는 처리할 문서의 DB Context와 공유 파일 경로를 전달하고, Worker는 Parsing부터 핵심정보 추출까지 실행해 결과를 반환합니다.

## 2. Endpoint

```text
POST /v1/documents/{document_id}/process
```

요청 예시:

```json
{
  "announcement_id": 1329,
  "announcement_key": "2015122300020722",
  "announcement_date": "2026-09-10",
  "source": {
    "filename": "입주자모집공고문.hwpx",
    "format": "hwpx",
    "storage_path": "/data/documents/.../입주자모집공고문.hwpx"
  },
  "start_stage": null
}
```

`document_id`와 `announcement_id`는 양수여야 하고, 형식은 `hwp` 또는 `hwpx`만 허용합니다.

## 3. 처리 순서

1. 공유 경로의 원본 파일 확인
2. 실제 HWP/HWPX 형식 확인
3. Parser subprocess 실행
4. Normalizer subprocess 실행
5. Structure·Verification subprocess 실행
6. Chunking subprocess 실행
7. Embedding Service HTTP 호출
8. Embedding 산출물 저장
9. 핵심정보 Python 함수 호출
10. 완료 응답 반환

## 4. 성공 응답

```json
{
  "document_id": 2100,
  "announcement_id": 1329,
  "announcement_key": "2015122300020722",
  "status": "completed",
  "document_format": "hwpx",
  "output_path": "/app/outputs/.../document_2100",
  "summary": {
    "chunk_count": 100,
    "embedding_count": 100
  },
  "key_information": {
    "application_period": {},
    "eligibility": {},
    "supply_information": {},
    "income_asset_criteria": {},
    "required_documents": {},
    "winner_announcement": {},
    "contact_information": {}
  }
}
```

## 5. 오류 응답

Worker는 단계에 맞는 `error.code`와 `error.message`를 반환합니다. Backend는 오류 코드를 `format_detection`, `parser`, `normalizer`, `structure`, `verification`, `chunking`, `embedding`, `key_information` 등의 단계로 매핑해 ErrorLog에 저장합니다.

## 6. Embedding 연결

Worker는 Chunk의 순서만 믿지 않고 각 요청 Item에 고유 ID를 보냅니다. Embedding 응답의 ID와 요청 ID를 비교해 Vector가 올바른 Chunk에 연결됐는지 확인합니다. Chunk 수와 Embedding 수가 다르거나 Vector 차원이 잘못되면 성공으로 처리하지 않습니다.

Docker 주소는 `http://embedding:18001`, Host 확인 주소는 `127.0.0.1:18001`입니다.

## 7. 재시작 단계

`start_stage`가 지정되면 Worker는 그 단계 이전에 필요한 산출물이 존재하는지 확인합니다. 필요한 파일이 없으면 중간 단계부터 억지로 실행하지 않고 오류를 반환합니다.

## 8. 핵심 파일

- `document_worker/main.py`
- `document_worker/api/routes.py`
- `document_worker/api/schemas.py`
- `document_worker/service.py`
- `backend/app/clients/document_worker_client.py`
- `backend/app/services/document_processing_service.py`

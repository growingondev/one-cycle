# Backend–Crawler HTTP 연동 기록

## 작업 범위

- 작업 브랜치: `feat/backend-crawler-http-integration`
- 기준: `develop-api`의 Worker 출력 경로 매핑 병합 이후
- 목적: Backend가 Crawler Python 함수를 직접 import하지 않고 HTTP Job API로 호출

## 변경 내용

- `backend/app/clients/crawler_client.py` 추가
  - 전체 수집·개별 재수집 Job 생성
  - `queued → running → completed` 상태 폴링
  - 결과·실패 코드·타임아웃 검증
- `collection_service.py`
  - `crawler.crawler` 직접 호출 제거
  - `crawler_client` 사용
- `http_json.py`
  - GET 지원
  - FastAPI `detail` 오류 형식 지원
- 관리자 API
  - Crawler busy: 409
  - 잘못된 응답·작업 실패: 502
  - 연결 실패·타임아웃: 503
- Docker
  - Crawler를 `127.0.0.1:18004`로 분리
  - Crawler·Backend가 `/data/documents` 공유
  - Backend 이미지의 Chrome·Selenium·webdriver-manager 제거
- 관련 테스트·Backend 연결 문서 갱신

## 현재 호출 흐름

```text
Admin API
 → pipeline_gateway
 → integration_service
 → collection_service
 → crawler_client
 → Crawler HTTP Job API
 → 상태 폴링 및 결과 조회
 → 기존 DB 저장·문서 처리·Publish
```

## 검증 결과

- Crawler HTTP 관련 테스트: 24/24 통과
- Backend 전체 테스트: 139개 중 135개 통과
- 기존 실패 4개: Key Information Extractor의 날짜·공급정보 추출 테스트
- Docker Compose 설정: 통과
- 실제 Crawler 이미지 빌드 및 50건 E2E: 미실행

## 제한사항

- Backend는 현재 Crawler Job이 끝날 때까지 관리자 요청에서 동기 폴링한다.
- Crawler Job 상태는 메모리에만 저장되므로 컨테이너 재시작 시 사라진다.
- 실제 Docker 빌드·수집 E2E는 AWS 평가 작업 종료 후 진행한다.

# Backend E2E Hotfix 검증 - 2026-09-02

## 작업 배경

AWS Collection E2E에서 크롤링은 완료됐지만 문서 처리 45건이 모두 실패했다.

주요 원인은 다음과 같았다.

- Backend Docker 이미지의 NumPy 의존성 누락
- `신청양식` 문서가 `unknown`으로 분류되어 Publish 차단
- Worker 오류가 실제 처리 단계가 아닌 `integration` 오류로 기록될 가능성
- Backend와 Document Worker 사이의 결과물 경로 공유 필요

## 변경 내용

- `infra/backend/requirements.txt`
  - `numpy==2.5.1` 추가
- `document_role_service.py`
  - `신청양식`을 `supporting` 키워드로 추가
- `document_processing_service.py`
  - `InternalServiceHTTPError` 처리
  - Worker 오류 코드를 parser, normalizer, structure, verification, chunking, embedding 등의 실제 단계로 변환
  - Worker의 원래 `error_code`와 `message` 유지
- `integration_service.py`
  - Worker 핵심정보 추출 실패를 `key_information_extraction / structuring`으로 분류
  - Backend 핵심정보 저장 실패인 `key_information / database`와 구분
- `infra/docker-compose.yml`
  - Backend와 Document Worker에 `/app/outputs` 공유 볼륨 추가

AWS에 있던 `docker/llm/Dockerfile` 변경은 이번 브랜치에서 제외했다.

## AWS 검증 결과

- 공고 수집: 50건
- 전체 문서: 89건
- 분석 대상 문서: 45건
- 문서 처리: 45/45 성공
- Chunk: 11,712건
- Embedding: 11,712건
- Publish: 성공
- Active CollectionRun: 5
- 사용자 공고 API: HTTP 200, 총 50건 조회

기존 DB에서 `unknown`이었던 `document_id=186`은 Runtime 검증을 위해 `supporting`으로 보정했다. 이후 새로 수집되는 문서는 변경된 분류 규칙을 적용받는다.

## 로컬 검증 결과

- 이번 변경 관련 테스트: 33/33 통과
- Docker Compose 설정 검증: 통과
- Backend 전체 테스트: 124개 중 4개 실패

전체 테스트의 실패 4개는 기존 Key Information Extractor의 날짜·공급정보 추출 테스트이며 이번 핫픽스 변경 범위와는 무관하다.

## 후속 작업

- 기존 Key Information Extractor 테스트 실패 4건 별도 확인
- 미지원 문서로 내용이 비어 있는 공고의 관리자 숨김 기능 검토
- llama.cpp 빌드 안정화 변경은 별도 브랜치에서 처리

# GitHub Actions CI

## 목적

이 워크플로는 Pull Request와 통합 브랜치에서 기본 회귀 오류를 빠르게 확인한다.
현재 단계에서는 검증만 수행하며 AWS, Vercel 또는 `main` 운영 환경에 배포하지 않는다.

## 실행 조건

- `develop-api` 대상 Pull Request
- `main` 대상 Pull Request
- `develop-api` push
- `main` push
- GitHub Actions 화면의 수동 실행

현재 팀 통합 브랜치는 `develop-api`이다. 모든 기능 통합이 끝난 뒤 `main`을 운영 브랜치로
사용해도 같은 CI를 재사용할 수 있다.

## 검사 항목

### Python

- Backend, Crawler, Document Worker의 경량 의존성만 설치
- 치명적인 Python 문법 및 이름 오류 Ruff 검사
- Backend, Crawler, Document Worker 단위 테스트
- Python 소스 컴파일 검사
- Alembic 전체 migration chain SQL 생성
- Docker Compose 구성 검증

GPU, CUDA, 모델 파일을 요구하는 전체 `requirements.txt`는 설치하지 않는다.

### Frontend

- User frontend `npm ci` 및 production build
- Admin frontend `npm ci`, lint 및 production build

`npm audit` 결과는 의존성 업데이트 작업으로 별도 관리한다. CI에서 자동 수정하지 않는다.

## 현재 기준선 예외

### 핵심정보 추출 테스트 4개

최신 `develop-api`에서 아래 테스트 4개는 CI 도입 전부터 실패한다.

- `test_application_period`
- `test_application_period_korean_ampm_range`
- `test_application_period_labeled_range`
- `test_supply_summary_is_compact`

워크플로는 해당 테스트 ID만 `--deselect`하고 나머지 테스트는 모두 실행한다. 추출 로직과
기대값이 정리되면 네 개의 `--deselect` 옵션을 제거한다.

### SQLAlchemy 모델의 Ruff F821

`backend/app/models/*.py`는 순환 관계를 피하기 위해 SQLAlchemy 관계 대상을 문자열 타입으로
참조한다. 이 경로에 한해 `F821`을 예외 처리한다. 다른 Python 경로에서 발생한 `F821`은
계속 CI 실패로 처리한다.

## 현재 CI에서 제외하는 항목

- 실제 LH 사이트 크롤링
- 실제 PostgreSQL 데이터 변경 테스트
- GPU 임베딩 모델 로딩
- LLM 및 RAG E2E 평가
- Docker GPU 이미지 전체 빌드
- AWS 배포
- Vercel 배포
- Nginx 설정 변경

실제 서비스 통합 검증과 배포 자동화는 서비스 구성이 확정된 뒤 별도 CD 워크플로로 추가한다.

## 향후 CD 원칙

- 기능 브랜치에서 `develop-api`로 병합할 때는 CI만 실행한다.
- 최종 운영 전환 시 `develop-api`에서 `main`으로 Pull Request를 생성한다.
- `main` 병합 후 배포하는 CD는 Nginx, 도메인, HTTPS, Vercel 환경 변수가 확정된 뒤 추가한다.
- CD를 추가하기 전에는 이 워크플로가 운영 서버를 변경하지 않는다.

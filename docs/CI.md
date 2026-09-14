# GitHub Actions CI/CD

## 1. 목적

DDOKBOT은 기능 통합 검증과 AWS 운영 배포를 GitHub Actions로 관리합니다.

- CI: Pull Request와 통합 브랜치의 회귀 오류 검사
- CD: `main` CI 성공 후 AWS Docker 서비스 배포
- Frontend 배포: Vercel Git 연동

기능 브랜치의 코드는 먼저 `develop-api`에서 검증하고, 최종 운영 반영은 `main` Pull Request를 통해 진행합니다.

## 2. 브랜치 흐름

```text
feature/* 또는 fix/*
        ↓ Pull Request + CI
develop-api
        ↓ 통합 확인 후 Pull Request + CI
main
        ↓ CI 성공
AWS CD
```

## 3. CI

기준 파일:

```text
.github/workflows/ci.yml
```

### 실행 조건

- `develop-api` 대상 Pull Request
- `main` 대상 Pull Request
- `develop-api` Push
- `main` Push
- GitHub Actions 화면의 수동 실행

### Python 검사

- Backend, Crawler, Document Worker 경량 의존성 설치
- Ruff를 이용한 치명적 문법·이름 오류 검사
- Backend, Crawler, Document Worker 테스트
- Python 소스 컴파일 검사
- Alembic Migration 전체 체인의 SQL 생성
- Docker Compose 구성 검증

GPU, CUDA, Embedding 모델, GGUF 모델을 요구하는 전체 AI 실행 환경은 경량 CI에 설치하지 않습니다.

### Frontend 검사

- 사용자 Frontend: `npm ci`, Production Build
- 관리자 Frontend: `npm ci`, Lint, Production Build

### 현재 기준선 예외

다음 핵심정보 추출 테스트 4개는 CI 도입 전부터 기대값 정리가 완료되지 않아 현재 Workflow에서 `--deselect` 처리되어 있습니다.

- `test_application_period`
- `test_application_period_korean_ampm_range`
- `test_application_period_labeled_range`
- `test_supply_summary_is_compact`

따라서 CI 성공은 위 4개를 제외한 현재 검증 범위가 통과했다는 의미입니다. 추출 로직과 기대값을 정리한 뒤 예외를 제거해야 합니다.

SQLAlchemy Model의 문자열 관계 타입으로 인한 `F821`은 `backend/app/models/*.py`에만 예외를 적용합니다.

### CI에서 수행하지 않는 검사

- 실제 LH 사이트 크롤링
- 운영 PostgreSQL 데이터 변경
- GPU Embedding 모델 로딩
- llama.cpp 모델 로딩
- 실제 RAG·LLM E2E 품질 평가
- Docker GPU 이미지 전체 빌드
- 운영 데이터 수집 및 Publish

이 항목들은 배포 환경의 Health Check와 별도 E2E 검증으로 확인합니다.

## 4. AWS CD

기준 파일:

```text
.github/workflows/deploy-aws.yml
```

### 실행 조건

- `main`에서 실행된 `CI` Workflow가 성공한 경우
- GitHub Actions 화면에서 수동 실행한 경우

중복 배포는 `deploy-aws-production` Concurrency Group으로 제어하며, 진행 중인 배포를 자동 취소하지 않습니다.

### 배포 과정

1. Repository Secret으로 SSH Key 준비
2. AWS 서버에 SSH 접속
3. 추적 중인 파일에 커밋되지 않은 변경이 없는지 확인
4. `origin/main` Fetch 및 Fast-forward Pull
5. Docker 이미지 빌드
6. Alembic Migration 적용
7. 서비스 컨테이너 재생성
8. Nginx 재시작
9. 내부·외부 Health Check
10. Docker 서비스 상태와 배포 Commit 출력

### 자동 빌드 대상

- `nginx`
- `backend`
- `crawler`
- `document-worker`
- `rag`

### 자동 재시작 대상

- `nginx`
- `backend`
- `crawler`
- `scheduler`
- `document-worker`
- `rag`

Embedding과 LLM 컨테이너는 모델 크기와 GPU 운영 시간을 고려해 현재 CD의 자동 빌드·재생성 대상에서 제외되어 있습니다. 해당 Dockerfile, 의존성 또는 모델 설정을 변경한 경우 AWS에서 별도로 빌드하고 재생성해야 합니다.

### Health Check

배포 Workflow는 다음 항목을 확인합니다.

- Backend API
- PostgreSQL 연결
- Crawler
- Document Worker OpenAPI
- RAG Service
- Public API
- 사용자 Vercel 도메인의 API 연결
- 관리자 Vercel 도메인의 API 연결

각 내부 서비스는 최대 30회, 5초 간격으로 응답을 기다립니다.

## 5. Vercel Frontend 배포

- 사용자 Frontend Root Directory: `frontend/user`
- 관리자 Frontend Root Directory: `frontend/admin`
- 사용자 서비스: https://ddokbot.codefoilo.store/
- 관리자 서비스: https://ddokbot.admin.codefoilo.store/

두 Frontend의 `/api/*` 요청은 Vercel Rewrite를 통해 AWS Public API로 전달됩니다.

## 6. 필요한 Repository Secrets

AWS CD에는 다음 GitHub Actions Repository Secret이 필요합니다.

| Secret | 내용 |
|---|---|
| `AWS_HOST` | AWS 서버 주소 |
| `AWS_USER` | SSH 사용자 |
| `AWS_SSH_PRIVATE_KEY` | GitHub Actions 배포용 SSH Private Key |

Secret의 실제 값은 README, 문서, Commit, Actions Log에 출력하지 않습니다.

## 7. 현재 제한사항

- 자동 Rollback은 구현되어 있지 않습니다.
- Embedding·LLM 이미지는 자동 재빌드하지 않습니다.
- 운영 배포 전 전체 GPU E2E를 CI에서 수행하지 않습니다.
- AWS 작업 디렉터리에 추적 파일 변경이 있으면 배포를 중단합니다.
- Vercel 배포와 AWS CD는 서로 다른 배포 과정으로 실행됩니다.

배포 실패 시 Actions Log에서 실패 단계를 확인하고, AWS의 기존 컨테이너 상태와 `main` Commit을 대조해야 합니다.

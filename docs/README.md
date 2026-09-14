# DDOKBOT 문서 안내

이 폴더에는 현재 시스템을 설명하는 기준 문서와 개발 과정에서 작성한 작업 기록이 함께 있습니다. 처음 프로젝트를 확인하는 경우 아래의 **현재 기준 문서**부터 읽어 주세요.

> 기준 브랜치: `develop-api`
> 최종 제출·운영 브랜치: `main`

## 빠른 시작

| 알고 싶은 내용 | 먼저 읽을 문서 |
|---|---|
| 프로젝트 전체 개요 | [루트 README](../README.md) |
| Backend와 DB | [BACKEND.md](BACKEND.md), [DATABASE.md](DATABASE.md) |
| 전체 문서 처리 | [DOCUMENT_PROCESSING.md](DOCUMENT_PROCESSING.md) |
| Chunking과 Embedding | [CHUNKING.md](CHUNKING.md), [EMBEDDING.md](EMBEDDING.md) |
| 검색과 답변 생성 | [RAG.md](RAG.md) |
| Docker AI 서비스 | [DOCKER_AI_SERVICES.md](DOCKER_AI_SERVICES.md) |
| Frontend | [FRONTEND.md](FRONTEND.md) |
| 실행 환경 | [ENVIRONMENT.md](ENVIRONMENT.md) |
| 평가 | [EVALUATION.md](EVALUATION.md), [EVALUATION_GUIDE.md](EVALUATION_GUIDE.md) |
| CI/CD | [CI_CD.md](CI_CD.md) |
| 오래된 CollectionRun 정리 | [COLLECTION_RUN_RETENTION.md](COLLECTION_RUN_RETENTION.md) |

## 현재 기준 문서

다음 문서는 현재 코드와 운영 구조를 설명하는 문서로 관리합니다. 기능이 변경되면 함께 갱신해야 합니다.

### Backend · Database

- [BACKEND.md](BACKEND.md): 사용자·관리자 API, Service 계층, 공고 수집과 문서 처리, 오류 관리
- [BACKEND_INTEGRATION.md](BACKEND_INTEGRATION.md): Backend가 Crawler, Document Worker, RAG를 연결하는 통합 흐름
- [DATABASE.md](DATABASE.md): PostgreSQL·pgvector, ORM Model, 주요 테이블 관계와 활성 Run
- [SERVICE_API_CONTRACT.md](SERVICE_API_CONTRACT.md): 내부 HTTP Service의 요청·응답 및 오류 계약

### Document Intelligence Pipeline

- [DOCUMENT_PROCESSING.md](DOCUMENT_PROCESSING.md): 형식 확인, Parsing, Normalization, Structure, Verification 전체 흐름
- [DOCUMENT_WORKER.md](DOCUMENT_WORKER.md): Document Worker의 책임, API와 Backend 연결
- [CHUNKING.md](CHUNKING.md): 구조를 유지한 Chunk 생성과 Metadata
- [EMBEDDING.md](EMBEDDING.md): BGE-M3 Embedding Service와 Document Worker 연동

### RAG · LLM

- [RAG.md](RAG.md): Backend `rag_http` 호출, Vector Search, BM25, RRF, Prompt와 LLM 생성
- [DOCKER_AI_SERVICES.md](DOCKER_AI_SERVICES.md): Embedding, RAG, llama.cpp 컨테이너와 GPU·모델 Mount

### Frontend

- [FRONTEND.md](FRONTEND.md): 사용자·관리자 React 화면, API 호출과 주요 UI 데이터 흐름

### 실행 · 운영

- [ENVIRONMENT.md](ENVIRONMENT.md): 로컬·AWS 환경변수와 실행 조건
- [CI_CD.md](CI_CD.md): GitHub Actions 검증과 AWS 배포 흐름
- [COLLECTION_RUN_RETENTION.md](COLLECTION_RUN_RETENTION.md): 활성·직전 CollectionRun 보존과 이전 Run 정리

### Evaluation

- [EVALUATION.md](EVALUATION.md): 평가 목적, Dataset과 주요 평가 지표
- [EVALUATION_GUIDE.md](EVALUATION_GUIDE.md): 평가 전용 DB·Docker 환경과 실행 절차
- [EVALUATION_DATA_WORKFLOW.md](EVALUATION_DATA_WORKFLOW.md): Backend·DB 관점의 평가 데이터 등록과 발행 흐름

## 개발 과정 기록

다음 문서는 특정 기능을 구현하거나 장애를 해결했던 시점의 기록입니다. 현재 구조를 파악하는 첫 문서로 사용하지 않습니다. 삭제하지 않고 `docs/archive/`에 보존합니다.

### API·서비스 분리 기록

- [API_MIGRATION_HISTORY.md](archive/API_MIGRATION_HISTORY.md)
- [BACKEND_CRAWLER_HTTP_INTEGRATION_20260902.md](archive/BACKEND_CRAWLER_HTTP_INTEGRATION_20260902.md)
- [BACKEND_DB_INTEGRATION_HISTORY.md](archive/BACKEND_DB_INTEGRATION_HISTORY.md)

### 검증·오류 수정 기록

- [BACKEND_DB_RUNTIME_VALIDATION_20260826.md](archive/BACKEND_DB_RUNTIME_VALIDATION_20260826.md)
- [BACKEND_DOCUMENT_PROCESSING_AUTO_RETRY_20260904.md](archive/BACKEND_DOCUMENT_PROCESSING_AUTO_RETRY_20260904.md)
- [BACKEND_E2E_HOTFIX_VALIDATION_20260902.md](archive/BACKEND_E2E_HOTFIX_VALIDATION_20260902.md)
- [DOCUMENT_ROLE_CLASSIFICATION_FIX_20260907.md](archive/DOCUMENT_ROLE_CLASSIFICATION_FIX_20260907.md)

### 전체수집 복원 기록

- [FULL_COLLECTION_HANDOFF_20260904.md](archive/FULL_COLLECTION_HANDOFF_20260904.md)
- [FULL_COLLECTION_RESTORE.md](archive/FULL_COLLECTION_RESTORE.md)

## 문서 관리 원칙

1. 루트 `README.md`는 제출자·평가자가 처음 보는 프로젝트 소개로 유지합니다.
2. 현재 동작을 설명하는 문서는 실제 코드와 `infra/docker-compose.yml`을 기준으로 작성합니다.
3. 작업 과정, 일회성 검증 명령, 과거 경로는 현재 기준 문서와 분리합니다.
4. 기능을 변경한 Pull Request에는 관련 문서 갱신 여부를 함께 확인합니다.
5. 운영 비밀번호, SSH Key, 실제 `.env` 값은 문서와 저장소에 기록하지 않습니다.
6. 문서 링크를 추가하거나 파일을 이동한 뒤에는 상대 링크가 깨지지 않았는지 확인합니다.

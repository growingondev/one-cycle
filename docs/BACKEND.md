# Backend/API

## 1. 역할

Backend는 사용자·관리자 요청을 받는 FastAPI 애플리케이션이자, PostgreSQL과 내부 HTTP 서비스를 연결하는 조정 계층입니다.

```text
Frontend
  → Nginx 또는 Vercel /api Rewrite
  → FastAPI Route
  → Service
  → PostgreSQL 또는 내부 HTTP Client
```

Backend 진입점은 `backend/app/main.py`이며, `application.include_router(api_router)`로 `/api` Router를 연결합니다.

## 2. 계층별 책임

| 구성 | 위치 | 책임 |
|---|---|---|
| Route | `backend/app/api/routes/` | HTTP 요청 수신, 입력 전달, 상태 코드 반환 |
| Schema | `backend/app/schemas/` | 요청 검증과 응답 형식 정의 |
| Service | `backend/app/services/` | 업무 규칙, DB 작업, 내부 서비스 호출 조정 |
| Client | `backend/app/clients/` | Crawler·Worker·RAG HTTP 통신 |
| Model | `backend/app/models/` | SQLAlchemy ORM과 테이블 구조 |
| DB Session | `backend/app/db/` | PostgreSQL 연결과 Transaction Session |

Schema는 독립적인 실행 단계가 아니라 Route의 입력과 출력 형식을 정의합니다.

## 3. Router

`backend/app/api/router.py`가 다음 Router를 `/api` 아래에 연결합니다.

| 영역 | 주요 경로 |
|---|---|
| 상태 확인 | `GET /api/health`, `GET /api/health/db` |
| 사용자 공고 | `GET /api/announcements`, 상세·다운로드 |
| 사용자 Chat | `POST /api/chat` |
| 사용자 용어사전 | `GET /api/glossary` |
| 관리자 인증 | `/api/admin/auth/*` |
| 관리자 운영 | `/api/admin/*` |
| 관리자 용어사전 | `/api/admin/glossary/*` |

관리자 API는 `get_current_admin` 의존성을 통해 HttpOnly Cookie의 JWT를 검증합니다.

## 4. 내부 HTTP 서비스

| Client | 대상 | 기본 Docker 주소 |
|---|---|---|
| `crawler_client.py` | Crawler | `http://crawler:8000` |
| `document_worker_client.py` | Document Worker | `http://document-worker:18003` |
| `rag_client.py` | RAG Service | `http://rag:18002` |
| `http_json.py` | 공통 HTTP 처리 | 대상별 URL 사용 |

운영 기본 경로는 HTTP입니다. Chat의 `legacy` Python callable과 문서 재처리의 기존 callable은 Rollback 호환용으로 남아 있지만, Docker 운영 설정은 `RAG_RUNTIME=rag_http`, `DOCUMENT_PROCESSING_RUNTIME=worker_http`입니다.

## 5. 사용자 공고 조회

사용자 공고 API는 아무 CollectionRun이나 조회하지 않습니다. `system_state.active_collection_run_id`가 가리키는 활성 Run의 공고만 반환합니다.

```text
SystemState.active_collection_run_id
  → CollectionRun
  → Announcement
  → Document / KeyInformation
```

`GET /api/announcements?page=1&size=20`에서 `size`는 한 페이지에 반환할 공고 수입니다. `total_pages`는 전체 결과를 `size`개씩 나눴을 때 생기는 총 페이지 수입니다.

상세 조회는 공고 기본정보와 핵심정보를 먼저 읽고, 첨부문서 목록을 별도로 읽어 하나의 응답으로 합칩니다. 문서가 여러 개여도 공고 정보가 중복되지 않게 하기 위한 구조입니다. 핵심정보가 없어도 공고 자체는 조회할 수 있습니다.

다운로드는 같은 공고의 완료된 문서 중 `primary`를 우선하며, 없을 때 다른 완료 문서를 사용합니다.

## 6. Chat

```text
POST /api/chat
  → routes/chat.py
  → chat_service.answer_question_via_rag()
  → rag_client.answer_question()
  → POST RAG /v1/rag/answer
```

현재 기본값은 `RAG_RUNTIME=rag_http`입니다. RAG Service가 사용할 수 없으면 Backend는 사용자에게 503으로 변환해 반환합니다.

## 7. 전체 수집과 Publish

관리자 수집 또는 Scheduler는 `integration_service.collect_persist_and_process()`를 실행합니다.

1. Crawler Job 실행 및 결과 대기
2. CollectionRun·Announcement·Document 저장
3. `primary`이면서 다운로드가 완료된 문서 처리
4. Worker 결과 검증 및 Pipeline 산출물 저장
5. 모든 발행 조건 검증
6. 새 CollectionRun Publish
7. 설정에 따라 과거 Run 정리

문서 하나라도 발행 조건을 충족하지 못하면 새 CollectionRun은 Publish되지 않고 기존 활성 Run이 사용자에게 계속 제공됩니다.

## 8. 문서 역할

Crawler가 LH 상세페이지의 첨부 영역을 기준으로 역할을 전달합니다.

| LH 영역 | `document_role` | 전체 수집 자동 처리 |
|---|---|---:|
| 공고문 | `primary` | O |
| 다운로드 | `supporting` | X |
| 판정 불가 | `unknown` | X |

Backend는 전달된 역할이 `primary`, `supporting`, `unknown` 중 하나인지 검증해 저장합니다. 구버전 Crawler 응답처럼 `document_role` 필드 자체가 없을 때만 파일명 분류를 호환 경로로 사용합니다.

## 9. Worker 결과 저장과 활성화

Worker가 성공 응답을 반환했다고 바로 사용자 데이터가 되는 것은 아닙니다. Backend가 요청한 문서·공고 ID와 응답 ID가 같은지, Chunk와 Embedding 수가 맞는지 확인한 뒤 저장합니다.

Worker는 파일명이나 DB 형식보다 실제 파일 내부 형식을 우선하여 Parser를 선택합니다. 따라서 DB의 `document_format`과 Worker 응답 형식은 다를 수 있습니다. Backend는 `document_id`, `announcement_id`, `announcement_key` 일치를 검증하지만, 유효한 `hwp` 또는 `hwpx`로 보정된 응답의 형식 차이는 정상 처리합니다.

```text
ProcessingRun
  → ProcessingArtifact
  → DocumentStructure
  → ChunkSet
  → Chunk
  → Embedding
  → KeyInformation
```

정상 저장 후 같은 문서의 이전 `ProcessingRun`과 `ChunkSet`의 active 상태를 해제하고 새 버전을 활성화합니다. ProcessingRun 활성화는 문서 한 건의 최신 처리 버전을 뜻하고, CollectionRun Publish는 공고 묶음 전체를 사용자에게 공개한다는 뜻입니다.

## 10. 재시도와 오류

문서 처리는 최초 실행을 포함해 기본 최대 3회 시도합니다. 실패 단계가 확인되면 가능한 경우 해당 단계부터 다시 시작합니다. 최종 실패는 `error_logs`에 단계, 오류 코드, 메시지, 대상 ID와 함께 기록합니다.

관리자 페이지에서는 오류 상태를 `미해결`, `해결중`, `해결완료`로 관리하고 지원되는 오류를 재시도할 수 있습니다. 개별 재처리에 성공해도 전체 CollectionRun이 자동 Publish되는 것은 아닙니다.

## 11. 핵심 코드

| 목적 | 파일 |
|---|---|
| 앱 진입점 | `backend/app/main.py` |
| Router 결합 | `backend/app/api/router.py` |
| 사용자 공고 | `routes/announcements.py`, `announcement_service.py` |
| Chat | `routes/chat.py`, `chat_service.py`, `rag_client.py` |
| 전체 수집 | `integration_service.py`, `collection_service.py` |
| Publish | `collection_publish_service.py` |
| Worker 연동 | `document_processing_service.py`, `document_worker_client.py` |
| 오류·재시도 | `error_log_service.py`, `error_retry_service.py` |
| 보관 정책 | `collection_retention_service.py` |

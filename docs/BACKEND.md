# DDOKBOT Backend

> 이 문서는 DDOKBOT Backend의 구조와 연결 관계를 설명합니다.
>
> 새로운 개발자 또는 AI가 다음 내용을 이해할 수 있도록 작성되었습니다.
>
> - FastAPI Application이 어디서 시작되는지
> - API Router가 어떻게 등록되는지
> - Route, Schema, Service의 역할이 어떻게 분리되는지
> - DB와 RAG, Pipeline이 Backend와 어디에서 연결되는지
> - 관리자 인증이 어디에서 처리되는지
> - 환경변수는 어디에서 사용되는지
> - 4xx/5xx 오류가 발생했을 때 어느 계층을 먼저 확인해야 하는지

---

# 1. Backend Stack

현재 Backend 주요 기술:

```text
FastAPI
Pydantic
Pydantic Settings
SQLAlchemy
PostgreSQL
pgvector
Alembic
```

Application Root:

```text
backend/app/
```

---

# 2. Backend Entry Point

FastAPI Application 진입점:

```text
backend/app/main.py
```

개념:

```text
main.py
  ↓
create_app()
  ↓
FastAPI(...)
  ↓
api_router 등록
  ↓
app
```

실제 실행 target:

```text
backend.app.main:app
```

---

# 3. Backend 실행

프로젝트 Root:

```bash
cd /home/ubuntu/ddokbot/one-cycle
```

프로젝트 Python:

```text
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python
```

실행 예:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m uvicorn backend.app.main:app \
--host 127.0.0.1 \
--port 8000
```

정상 실행 후 Backend는 개발 환경 기준:

```text
127.0.0.1:8000
```

에서 동작합니다.

---

# 4. Backend 전체 구조

```text
backend/app/
├── __init__.py
├── main.py
│
├── api/
│   ├── __init__.py
│   ├── dependencies.py
│   ├── router.py
│   └── routes/
│       ├── admin.py
│       ├── admin_auth.py
│       ├── announcements.py
│       ├── chat.py
│       └── health.py
│
├── core/
│   ├── __init__.py
│   └── config.py
│
├── db/
│   ├── __init__.py
│   ├── base.py
│   └── session.py
│
├── models/
├── schemas/
└── services/
```

---

# 5. Backend Layering

기본 계층 구조:

```text
HTTP Request
    ↓
Route
    ↓
Pydantic Schema
    ↓
Service
    ↓
DB / RAG / Pipeline
    ↓
Response
```

원칙:

```text
Route
→ HTTP 처리

Schema
→ 입력/출력 계약

Service
→ Application Logic

DB Model
→ Persistence Structure
```

복잡한 로직을 Route에 직접 넣지 않습니다.

---

# 6. main.py

파일:

```text
backend/app/main.py
```

역할:

```text
FastAPI Application 생성
       ↓
Application metadata 설정
       ↓
api_router 등록
       ↓
app 생성
```

현재 Application 설명:

```text
LH 공고문 기반 AI 질의응답 서비스 API
```

API 자체가 열리지 않는 경우 가장 먼저 확인할 파일 중 하나입니다.

---

# 7. API Router

파일:

```text
backend/app/api/router.py
```

전체 API prefix:

```text
/api
```

현재 등록되는 Router:

```text
health_router
announcement_router
chat_router
admin_auth_router
admin_router
```

구조:

```text
FastAPI App
    ↓
api_router
    ↓
/api
    ├── health
    ├── announcements
    ├── chat
    ├── admin/auth
    └── admin
```

---

# 8. Route Layer

위치:

```text
backend/app/api/routes/
```

현재 주요 Route:

```text
health.py
announcements.py
chat.py
admin_auth.py
admin.py
```

---

# 9. Health API

파일:

```text
backend/app/api/routes/health.py
```

확인된 Endpoint:

```text
GET /api/health
GET /api/health/db
```

목적:

```text
Application 상태 확인
DB 연결 상태 확인
```

Backend 전체가 이상할 때 Chat API부터 테스트하지 말고 Health부터 확인하는 것이 좋습니다.

예:

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

DB:

```bash
curl -i \
http://127.0.0.1:8000/api/health/db
```

---

# 10. Announcement API

파일:

```text
backend/app/api/routes/announcements.py
```

주요 Endpoint:

```text
GET /api/announcements

GET /api/announcements/{id}
```

연결:

```text
Frontend
   ↓
announcements.py
   ↓
announcement_service.py
   ↓
Database
```

---

# 11. Announcement Service

파일:

```text
backend/app/services/announcement_service.py
```

역할:

```text
공고 목록 조회
공고 상세 조회
DB 결과 가공
```

Frontend 목록 문제라면:

```text
ListScreen.tsx
↓
announcements.py
↓
announcement_service.py
↓
DB
```

순서로 확인합니다.

---

# 12. Chat API

파일:

```text
backend/app/api/routes/chat.py
```

Endpoint:

```text
POST /api/chat
```

Request:

```json
{
  "announcementId": 1,
  "question": "신청 일정은 언제인가?"
}
```

Route 내부 역할:

```text
ChatRequest
   ↓
answer_question_via_rag()
   ↓
ChatResponse
```

Route는 RAG 내부 Retrieval/Generation 구현을 직접 알지 않습니다.

---

# 13. Chat Schema

파일:

```text
backend/app/schemas/chat.py
```

현재 주요 Schema:

```text
ChatRequest
EvidenceItem
ChatResponse
```

---

## ChatRequest

개념:

```text
announcementId
question
```

Frontend JSON:

```json
{
  "announcementId": 1,
  "question": "질문"
}
```

내부 Python:

```text
announcement_id
question
```

---

## EvidenceItem

주요 Field:

```text
chunkId
sectionTitle
content
score
```

---

## ChatResponse

주요 Field:

```text
answer
grounded
evidence
```

이 Schema는 Frontend와 RAG 사이의 핵심 HTTP Contract입니다.

---

# 14. Chat Service

파일:

```text
backend/app/services/chat_service.py
```

Backend와 RAG 사이의 Adapter입니다.

흐름:

```text
chat.py
  ↓
answer_question_via_rag()
  ↓
_load_answer_question()
  ↓
RAG_ANSWER_FUNCTION
  ↓
rag.service:answer_question
```

---

# 15. RAG Dynamic Import

환경변수:

```text
RAG_ANSWER_FUNCTION
```

현재 값:

```text
rag.service:answer_question
```

형식:

```text
module.path:function_name
```

즉:

```text
rag.service
```

모듈에서:

```text
answer_question
```

함수를 동적으로 import합니다.

---

# 16. 왜 Dynamic Import를 사용하는가

Backend가 특정 RAG 구현 파일에 강하게 결합되는 것을 줄이기 위한 구조입니다.

예:

```text
현재:
rag.service:answer_question

향후:
new_rag.service:answer_question
```

으로 변경하더라도 Backend Route 자체는 유지할 수 있습니다.

단 함수 입력/출력 Contract는 유지해야 합니다.

---

# 17. RAG Function Contract

Backend가 기대하는 개념적 입력:

```python
answer_question(
    announcement_id=...,
    question=...,
)
```

반환은 다음과 호환되어야 합니다.

```text
ChatResponse
또는
ChatResponse로 validate 가능한 dict
```

예:

```python
{
    "answer": "...",
    "grounded": True,
    "evidence": [],
}
```

---

# 18. RAG 반환 형식 오류

`chat_service.py`는 RAG 결과가:

```text
ChatResponse
```

또는:

```text
dict
```

가 아니면 오류를 발생시킵니다.

따라서 RAG를 새로 구현할 때 임의 객체를 그대로 반환하면 안 됩니다.

최종 Backend Contract:

```text
answer
grounded
evidence
```

를 유지해야 합니다.

---

# 19. RAG Service Error와 HTTP

현재 Chat Route는:

```text
RagServiceUnavailableError
```

를 처리하여:

```text
503 Service Unavailable
```

로 변환할 수 있습니다.

즉 RAG function 자체를 import하지 못하거나
Backend Adapter 계층에서 사용할 수 없는 경우 503 계열 문제를 확인합니다.

---

# 20. RAG 내부 예외와 500

RAG 내부에서 처리되지 않은 예외가 Backend까지 올라오면:

```text
500 Internal Server Error
```

가 발생할 수 있습니다.

과거 실제 사례:

```text
GenerationError
→ RAGServiceError
→ FastAPI 500
```

처럼 Generation 문제로 Chat Endpoint 자체가 500을 반환한 적이 있습니다.

이후 Fallback 처리를 추가하여 HTTP 200으로 변경된 상태가 있었습니다.

따라서:

```text
HTTP 500
```

이면 반드시 Server Traceback을 확인합니다.

---

# 21. Pipeline Gateway

파일:

```text
backend/app/services/pipeline_gateway.py
```

Backend와 Pipeline 기능 사이의 Adapter/Gateway입니다.

환경변수 기반으로 외부 Pipeline 함수를 연결하는 패턴을 사용할 수 있습니다.

즉:

```text
Backend
  ↓
Pipeline Gateway
  ↓
Pipeline Function
```

형태로 책임을 분리합니다.

---

# 22. Pipeline Persistence

파일:

```text
backend/app/services/pipeline_persistence.py
```

Pipeline과 Database 사이의 핵심 연결점입니다.

흐름:

```text
Pipeline Outputs
      ↓
Validation
      ↓
ProcessingRun
      ↓
DocumentStructure
      ↓
ChunkSet
      ↓
Chunks
      ↓
Embeddings
      ↓
Database
```

이 파일은 일반 Runtime Chat Service가 아니라
문서 Ingestion/Persistence 기능에 속합니다.

---

# 23. Admin Authentication Route

파일:

```text
backend/app/api/routes/admin_auth.py
```

관리자 인증 관련 Endpoint가 위치합니다.

현재 Route 목록에서 확인된 기능:

```text
POST
GET
POST
```

형태의 Login/현재 사용자/Logout 계열 Endpoint가 존재합니다.

정확한 URL은 실제 `admin_auth.py`를 Source of Truth로 확인합니다.

---

# 24. Admin Authentication Service

파일:

```text
backend/app/services/admin_auth_service.py
```

현재 코드에서 확인된 주요 환경변수:

```text
ADMIN_ID
ADMIN_PASSWORD
ADMIN_JWT_SECRET
ADMIN_JWT_EXPIRE_SECONDS

ADMIN_COOKIE_SECURE
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SAMESITE
```

---

# 25. 관리자 인증 흐름

개념:

```text
Admin Login Form
      ↓
Admin Auth API
      ↓
admin_auth_service.py
      ↓
Credential Validation
      ↓
JWT
      ↓
Cookie
      ↓
Admin API
```

Frontend:

```text
frontend/admin/js/auth.js
```

와 연결됩니다.

---

# 26. 관리자 Secret 관리

다음 값은 Source Code에 하드코딩하지 않습니다.

```text
ADMIN_PASSWORD
ADMIN_JWT_SECRET
```

실제 값:

```text
.env
```

예제 변수명:

```text
.env.example
```

에 관리합니다.

---

# 27. Admin API

파일:

```text
backend/app/api/routes/admin.py
```

현재 다수의 관리자 Endpoint가 존재합니다.

기능 영역은 현재 코드 구조상 다음과 관련됩니다.

```text
공고 관리
문서 관리
Pipeline 처리 상태
파일 Download
오류 관리
상태 변경
재처리 기능
```

정확한 Endpoint URL과 HTTP Method는:

```text
backend/app/api/routes/admin.py
```

를 확인합니다.

---

# 28. Admin Service

파일:

```text
backend/app/services/admin_service.py
```

관리자 Route의 실제 Application Logic을 담당합니다.

개념:

```text
Admin Route
    ↓
Admin Service
    ↓
Database / Pipeline
```

관리자 화면 문제를 Route 하나만 보고 수정하지 않고 Service까지 확인합니다.

---

# 29. Backend Core Config

파일:

```text
backend/app/core/config.py
```

Pydantic Settings 기반 Application Configuration입니다.

현재 `.env` 로딩 경로:

```text
PROJECT_ROOT / ".env"
```

개념:

```text
.env
 ↓
Settings
 ↓
Backend
```

DB/Application 기본 설정 관련 문제는 이 파일을 확인합니다.

---

# 30. Environment Variable 직접 접근

현재 일부 Service에서는 Pydantic Settings 대신:

```python
os.getenv(...)
```

를 직접 사용합니다.

확인된 영역:

```text
chat_service.py
admin_auth_service.py
pipeline_gateway.py
rag/db_pipeline.py
rag/service.py
```

따라서 환경변수를 변경할 경우 `core/config.py`만 확인해서는 안 됩니다.

---

# 31. 주요 Backend/RAG 환경변수

현재 코드에서 확인된 주요 변수:

```text
RAG_ANSWER_FUNCTION
MVP_ANNOUNCEMENT_ID
RAG_DB_TOP_K
MVP_DOCUMENT_FORMAT
```

관리자:

```text
ADMIN_ID
ADMIN_PASSWORD
ADMIN_JWT_SECRET
ADMIN_JWT_EXPIRE_SECONDS
ADMIN_COOKIE_SECURE
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SAMESITE
```

정확한 전체 목록은 실제 코드와 `.env.example`을 기준으로 확인합니다.

---

# 32. Database Session

파일:

```text
backend/app/db/session.py
```

역할:

```text
Database Engine
SessionLocal
```

Backend Service와 RAG DB Pipeline에서 공통으로 사용합니다.

DB 관련 코드에서 별도 Engine을 중복 생성하지 않는 것이 좋습니다.

---

# 33. ORM Models

위치:

```text
backend/app/models/
```

주요 Model:

```text
Announcement
Document
DocumentStructure
ProcessingRun
ProcessingArtifact
ChunkSet
Chunk
Embedding
CollectionRun
SystemState
KeyInformation
Admin
ErrorLog
```

자세한 관계:

```text
docs/DATABASE.md
```

를 참고합니다.

---

# 34. Schemas

위치:

```text
backend/app/schemas/
```

Schema와 ORM Model은 같은 개념이 아닙니다.

```text
ORM Model
→ Database 구조

Pydantic Schema
→ API Request/Response 구조
```

예:

```text
backend/app/models/announcement.py
```

와:

```text
backend/app/schemas/announcement.py
```

는 역할이 다릅니다.

---

# 35. Announcement Schema

파일:

```text
backend/app/schemas/announcement.py
```

Frontend 공고 목록/상세가 사용하는 JSON 구조와 관련됩니다.

현재 확인된 주요 상세 영역:

```text
applicationPeriod
eligibility
supplyInformation
incomeAssetCriteria
requiredDocuments
winnerAnnouncement
contactInformation
documents
```

Frontend가 사용하는 Field와 이 Schema가 맞아야 합니다.

---

# 36. Common Schema

파일:

```text
backend/app/schemas/common.py
```

Pagination 등의 공통 API Schema를 정의합니다.

확인된 주요 Field:

```text
page
size
total
total_pages
```

---

# 37. Backend ↔ Frontend 연결

User Frontend API Base:

```text
/api
```

Frontend:

```text
frontend/user/src/config.ts
```

Backend:

```text
backend/app/api/router.py
```

둘이 다음처럼 연결됩니다.

```text
Frontend API_BASE_URL
        │
        ▼
       /api
        │
        ▼
FastAPI api_router
```

---

# 38. User Frontend API 호출

공고 목록:

```text
ListScreen.tsx
    ↓
GET /api/announcements
```

공고 상세:

```text
DetailScreen.tsx
    ↓
GET /api/announcements/{id}
```

Chat:

```text
DetailScreen.tsx
    ↓
POST /api/chat
```

---

# 39. Backend Port와 Frontend Proxy

Backend 개발 포트:

```text
8000
```

User Frontend는 `/api`를 사용하므로
Vite 개발 서버가 Backend로 Proxy해야 합니다.

관련 파일:

```text
frontend/user/vite.config.ts
```

개념:

```text
Browser
  ↓
Vite :5173
  ↓
/api
  ↓
FastAPI :8000
```

---

# 40. API가 안 될 때 Browser보다 curl을 먼저 사용

Frontend에서 문제가 생기면 Backend API를 직접 확인합니다.

Health:

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

Announcements:

```bash
curl -i \
http://127.0.0.1:8000/api/announcements
```

Chat:

```bash
curl -i \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{"announcementId":1,"question":"신청 일정은 언제인가?"}'
```

---

# 41. HTTP Status별 진단

## 200 OK

HTTP 연결 자체는 정상입니다.

그 다음 JSON 내용을 확인합니다.

---

## 404 Not Found

확인:

```text
URL
/api Prefix
Route 등록
Frontend API Base
Vite Proxy
```

---

## 422 Unprocessable Entity

Pydantic Request Validation 실패 가능성이 높습니다.

확인:

```text
Request JSON
Schema
Field alias
Required field
```

예:

```text
announcementId
question
```

---

## 500 Internal Server Error

Backend 내부 예외입니다.

확인:

```text
Uvicorn Traceback
Service
DB
RAG
Generation
```

HTTP Response만 보고 원인을 추측하지 않습니다.

---

## 503 Service Unavailable

현재 Chat 구조에서는 RAG Function 연결 실패 등 Backend Adapter 문제일 수 있습니다.

확인:

```text
RAG_ANSWER_FUNCTION
chat_service.py
rag/service.py
```

---

# 42. Chat 문제 진단

다음 순서로 확인합니다.

```text
POST /api/chat
       ↓
chat.py
       ↓
chat_service.py
       ↓
RAG_ANSWER_FUNCTION
       ↓
rag/service.py
       ↓
rag/db_pipeline.py
```

HTTP 500이면 Server Traceback에서 처음 발생한 Application Error를 찾습니다.

---

# 43. 공고 목록 문제 진단

```text
GET /api/announcements
       ↓
announcements.py
       ↓
announcement_service.py
       ↓
DB
```

Backend curl이 정상인데 Frontend에서만 실패한다면 Backend를 수정하지 않고:

```text
config.ts
vite.config.ts
ListScreen.tsx
```

를 확인합니다.

---

# 44. DB 문제 진단

```text
/api/health/db
```

부터 확인합니다.

직접 DB Test:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from sqlalchemy import text
from backend.app.db.session import engine

with engine.connect() as conn:
    value = conn.execute(
        text("SELECT 1")
    ).scalar_one()

print(value)
PY
```

정상:

```text
1
```

---

# 45. Backend를 수정할 때 API Contract 유지

Backend 내부 Service 구현을 변경하더라도
가능하면 Frontend API Contract는 유지합니다.

예:

```text
Before

POST /api/chat

{
  announcementId,
  question
}

After

동일 Contract 유지
```

그러면 Frontend 수정이 필요 없습니다.

---

# 46. RAG를 교체할 때 Backend Contract 유지

RAG 전체를 새로 구현하더라도:

```text
answer_question(
    announcement_id,
    question,
)
```

형태와 최종:

```text
answer
grounded
evidence
```

를 유지하면 Backend Route와 Frontend 변경을 최소화할 수 있습니다.

---

# 47. Database 구조 변경

ORM Model을 변경하면:

```text
backend/app/models/
```

만 수정하고 끝내지 않습니다.

반드시:

```text
migrations/
```

도 확인합니다.

자세한 내용:

```text
docs/DATABASE.md
```

---

# 48. Backend 코드 추가 위치

새 기능별 권장 위치:

| 기능 | 위치 |
|---|---|
| 새 HTTP Endpoint | `backend/app/api/routes/` |
| Request/Response Model | `backend/app/schemas/` |
| Application Logic | `backend/app/services/` |
| DB ORM | `backend/app/models/` |
| DB Migration | `migrations/versions/` |
| DB Session | 기존 `backend/app/db/session.py` 사용 |
| Application Config | `backend/app/core/config.py` |
| RAG 기능 | `rag/` |
| Pipeline 기능 | `pipeline/` |

---

# 49. 새 Route 추가 절차

개념적인 순서:

```text
1. Schema 작성
2. Service 작성
3. Route 작성
4. Router 등록
5. API 테스트
6. Frontend 연결
```

새 Route 파일을 만들었다면:

```text
backend/app/api/router.py
```

에서 Router가 실제 등록되었는지 반드시 확인합니다.

---

# 50. 새 DB Model 추가 절차

```text
1. backend/app/models/ 에 Model 작성
2. models/__init__.py 연결 확인
3. Alembic Migration 생성/작성
4. Migration Review
5. alembic upgrade head
6. Service 구현
7. API 연결
```

---

# 51. Backend Compile Test

대규모 리팩터링 이후:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m compileall -q \
backend \
config \
rag \
pipeline \
migrations \
run_pipeline.py

echo "EXIT=$?"
```

정상:

```text
EXIT=0
```

---

# 52. Import Test

중요 Service 직접 Import:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from backend.app.main import app
from backend.app.services.chat_service import (
    answer_question_via_rag,
)
from rag.service import answer_question

print("[OK] backend imports")
PY
```

---

# 53. Backend Smoke Test 순서

Backend를 수정한 후 최소:

```text
1. Python Compile
2. Import
3. /api/health
4. /api/health/db
5. /api/announcements
6. /api/announcements/{id}
7. /api/chat
8. Frontend 확인
```

순서로 검사합니다.

---

# 54. 관리자 기능 수정 시 확인할 영역

```text
backend/app/api/routes/admin.py
backend/app/api/routes/admin_auth.py

backend/app/schemas/admin.py
backend/app/schemas/admin_auth.py

backend/app/services/admin_service.py
backend/app/services/admin_auth_service.py

backend/app/models/admin.py
backend/app/models/error_log.py

frontend/admin/
```

관리자 UI와 Backend를 같이 변경해야 하는 경우 이 전체 Boundary를 확인합니다.

---

# 55. Pipeline 관련 관리자 기능

관리자에서 문서 재처리 또는 Pipeline 실행 기능을 제공한다면
다음 경계를 사용해야 합니다.

```text
Admin API
   ↓
Admin Service
   ↓
Pipeline Gateway
   ↓
Pipeline
```

Pipeline 구현을 Admin Route 안에 직접 복사하지 않습니다.

---

# 56. Backend Source of Truth

| 영역 | Source of Truth |
|---|---|
| FastAPI Entry | `backend/app/main.py` |
| API Router | `backend/app/api/router.py` |
| HTTP Routes | `backend/app/api/routes/` |
| Request/Response | `backend/app/schemas/` |
| Application Logic | `backend/app/services/` |
| Config | `backend/app/core/config.py` |
| DB Session | `backend/app/db/session.py` |
| ORM | `backend/app/models/` |
| RAG Adapter | `backend/app/services/chat_service.py` |
| RAG Entry | `rag/service.py` |
| Pipeline Gateway | `backend/app/services/pipeline_gateway.py` |
| Pipeline Persistence | `backend/app/services/pipeline_persistence.py` |
| Migration | `migrations/` |
| Environment | `.env`, `.env.example` |

---

# 57. AI에게 Backend 작업을 맡길 때

최소 제공:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/BACKEND.md
docs/API.md

backend/
```

DB 관련이면 추가:

```text
docs/DATABASE.md
migrations/
alembic.ini
```

RAG 관련이면 추가:

```text
docs/RAG.md
rag/
```

Pipeline 관련이면 추가:

```text
docs/PIPELINE.md
run_pipeline.py
pipeline/
```

---

# 58. AI가 Backend 수정 전에 확인할 질문

```text
1. 문제가 Route인가?
2. Schema Validation인가?
3. Service Logic인가?
4. DB인가?
5. RAG인가?
6. Pipeline인가?
7. Frontend Proxy인가?
8. HTTP Contract를 유지할 수 있는가?
```

문제 범위를 확인하지 않고 여러 계층을 동시에 수정하지 않습니다.

---

# 59. 핵심 Backend 흐름

사용자 공고 조회:

```text
Frontend
 ↓
/api/announcements
 ↓
Route
 ↓
Announcement Service
 ↓
Database
```

사용자 Chat:

```text
Frontend
 ↓
/api/chat
 ↓
Route
 ↓
Chat Service
 ↓
RAG Service
 ↓
DB RAG
 ↓
Generation
```

문서 Pipeline:

```text
Pipeline
 ↓
Pipeline Persistence
 ↓
Database
```

관리자:

```text
Admin Frontend
 ↓
Admin/Auth Routes
 ↓
Admin Services
 ↓
Database / Pipeline
```

---

# 60. 핵심 요약

DDOKBOT Backend의 중심 원칙은 다음입니다.

```text
Route
→ HTTP 책임

Schema
→ API 계약

Service
→ Application Logic

Model
→ DB 구조

RAG
→ 검색/생성

Pipeline
→ 문서 처리
```

특정 문제가 발생하면 이 책임 경계를 기준으로 문제 위치를 먼저 판단합니다.

예:

```text
HTTP 422
→ Schema

HTTP 500 + DB Error
→ DB/Service

HTTP 200 + 정확한 Evidence + 잘못된 Answer
→ Generation

curl 정상 + Browser 실패
→ Frontend/Proxy

Pipeline Output 정상 + Runtime 검색 실패
→ Persistence/Activation/RAG DB Retrieval
```

Backend 내부 구현을 변경하더라도 가능하면 API Contract를 유지하여
Frontend와 다른 계층으로 변경이 전파되지 않도록 합니다.
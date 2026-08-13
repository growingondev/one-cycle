# DDOKBOT API

> DDOKBOT Backend API 계약과 연결 구조를 설명하는 문서입니다.
>
> 이 문서의 목적은 개발자 또는 AI가 API 문제 발생 시
> `Frontend → Route → Schema → Service → DB/RAG`
> 흐름을 빠르게 추적할 수 있도록 하는 것입니다.
>
> 실제 API 구현의 최종 기준(Source of Truth)은
> `backend/app/api/routes/`와 `backend/app/schemas/`입니다.

---

# 1. API 전체 구조

DDOKBOT API는 FastAPI 기반입니다.

```text
Frontend
   ↓
/api/*
   ↓
FastAPI
   ↓
Route
   ↓
Schema
   ↓
Service
   ↓
DB / Pipeline / RAG
```

Backend Entry:

```text
backend/app/main.py
```

API Router:

```text
backend/app/api/router.py
```

Route:

```text
backend/app/api/routes/
```

---

# 2. API Route 구조

현재 Route 파일:

```text
backend/app/api/routes/
├── __init__.py
├── health.py
├── announcements.py
├── chat.py
├── admin.py
└── admin_auth.py
```

역할:

| 파일 | 역할 |
|---|---|
| `health.py` | Backend/DB 상태 확인 |
| `announcements.py` | 사용자 공고 조회 |
| `chat.py` | 공고 기반 RAG 질의응답 |
| `admin.py` | 관리자 기능 |
| `admin_auth.py` | 관리자 로그인/인증 |

---

# 3. API Schema 구조

```text
backend/app/schemas/
├── __init__.py
├── common.py
├── announcement.py
├── chat.py
├── admin.py
└── admin_auth.py
```

Schema는 API의 Request/Response 계약을 정의합니다.

따라서 Frontend와 Backend 사이의 Field가 맞는지 확인할 때
Route보다 먼저 Schema를 확인해도 됩니다.

---

# 4. Service 구조

```text
backend/app/services/
├── __init__.py
├── announcement_service.py
├── chat_service.py
├── admin_service.py
├── admin_auth_service.py
├── pipeline_gateway.py
└── pipeline_persistence.py
```

개념:

```text
Route
  ↓
Service
  ↓
실제 Business Logic
```

Route에 복잡한 DB/RAG Logic을 직접 작성하지 않는 것을 원칙으로 합니다.

---

# 5. Health API

Route:

```text
backend/app/api/routes/health.py
```

현재 확인된 Endpoint:

```text
GET /api/health
GET /api/health/db
```

※ 정확한 Router Prefix는 `backend/app/api/router.py`와
각 Route의 `APIRouter(...)` 설정을 최종 기준으로 합니다.

---

# 6. Backend Health 확인

예:

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

이 API는 Backend Server 자체가 정상적으로 요청을 받고 있는지
확인할 때 사용합니다.

---

# 7. DB Health 확인

```bash
curl -i \
http://127.0.0.1:8000/api/health/db
```

개념:

```text
curl
 ↓
FastAPI
 ↓
DB Health Route
 ↓
SQLAlchemy
 ↓
PostgreSQL
```

Backend는 살아 있지만 DB 연결이 의심될 경우 사용합니다.

---

# 8. Announcement API

Route:

```text
backend/app/api/routes/announcements.py
```

Service:

```text
backend/app/services/announcement_service.py
```

Schema:

```text
backend/app/schemas/announcement.py
```

Frontend:

```text
frontend/user/src/components/screens/ListScreen.tsx
frontend/user/src/components/screens/DetailScreen.tsx
```

---

# 9. 공고 목록 조회

```text
GET /api/announcements
```

사용 목적:

```text
사용자 공고 목록 화면
```

Frontend:

```text
ListScreen.tsx
```

호출:

```typescript
fetch(`${API_BASE_URL}/announcements`)
```

여기서:

```text
API_BASE_URL = /api
```

입니다.

---

# 10. 공고 목록 Response

Frontend에서 현재 기대하는 핵심 구조:

```json
{
  "items": []
}
```

Frontend는:

```text
data.items
```

가 배열인지 확인합니다.

따라서 API가 HTTP 200이어도 다음처럼 반환하면 Frontend와 계약이 맞지 않습니다.

```json
[
  {}
]
```

Frontend 기준으로는:

```json
{
  "items": [
    {}
  ]
}
```

형태가 필요합니다.

실제 전체 Response Field는
`backend/app/schemas/announcement.py`를 최종 기준으로 확인합니다.

---

# 11. 공고 목록 연결

```text
ListScreen.tsx
      ↓
GET /api/announcements
      ↓
announcements.py
      ↓
announcement_service.py
      ↓
SQLAlchemy
      ↓
PostgreSQL
```

---

# 12. 공고 상세 조회

```text
GET /api/announcements/{id}
```

Frontend:

```text
DetailScreen.tsx
```

호출 개념:

```typescript
fetch(
  `${API_BASE_URL}/announcements/${notice.id}`
)
```

---

# 13. 공고 상세 연결

```text
사용자가 공고 선택
       ↓
DetailScreen
       ↓
GET /api/announcements/{id}
       ↓
announcements.py
       ↓
announcement_service.py
       ↓
PostgreSQL
```

---

# 14. Announcement Schema

파일:

```text
backend/app/schemas/announcement.py
```

현재 확인된 주요 상세 정보 Field:

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

이 Field들은 공고 상세 화면에서 사용할 수 있는 구조화 정보입니다.

---

# 15. Chat API

Route:

```text
backend/app/api/routes/chat.py
```

Schema:

```text
backend/app/schemas/chat.py
```

Service:

```text
backend/app/services/chat_service.py
```

RAG Entry:

```text
rag/service.py
```

Frontend:

```text
frontend/user/src/components/screens/DetailScreen.tsx
```

---

# 16. Chat Endpoint

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

---

# 17. Chat Request Schema

파일:

```text
backend/app/schemas/chat.py
```

현재 핵심 구조:

```python
announcement_id: int = Field(alias="announcementId")
question: str
```

즉 Python 내부에서는:

```text
announcement_id
```

Frontend JSON에서는:

```text
announcementId
```

를 사용합니다.

이 차이를 임의로 변경하지 않습니다.

---

# 18. Question 제한

현재 `question` Schema에는 길이 제한이 존재합니다.

```text
최소 길이: 1
최대 길이: 2000
```

잘못된 Request는 FastAPI/Pydantic Validation에 의해
HTTP 422가 발생할 수 있습니다.

---

# 19. Chat Response

현재 핵심 Response 구조:

```json
{
  "answer": "...",
  "grounded": true,
  "evidence": []
}
```

---

# 20. Evidence Schema

현재 Evidence의 주요 Field:

```text
chunkId
sectionTitle
content
score
```

예:

```json
{
  "chunkId": "document_sec_001_tbl_001",
  "sectionTitle": "신청 일정",
  "content": "신청 일정은 ...",
  "score": 0.58
}
```

---

# 21. Chat 전체 연결

```text
DetailScreen.tsx
      ↓
POST /api/chat
      ↓
chat.py
      ↓
chat_service.py
      ↓
rag.service.answer_question()
      ↓
DBRAGPipeline
      ↓
Query Embedding
      ↓
PostgreSQL + pgvector
      ↓
Generation
      ↓
ChatResponse
      ↓
DetailScreen
```

---

# 22. Chat Route 역할

`chat.py`는 RAG 자체를 구현하는 파일이 아닙니다.

역할:

```text
Request 수신
↓
Schema Validation
↓
chat_service 호출
↓
Response 반환
```

RAG 구현은:

```text
rag/
```

에 위치합니다.

---

# 23. Chat Service

파일:

```text
backend/app/services/chat_service.py
```

이 Service는 RAG Entry Function을 동적으로 연결할 수 있습니다.

환경변수:

```text
RAG_ANSWER_FUNCTION
```

현재 프로젝트의 정상 연결 대상은:

```text
rag.service:answer_question
```

형태를 기준으로 사용합니다.

---

# 24. RAG 연결

```text
chat_service.py
      ↓
RAG_ANSWER_FUNCTION
      ↓
rag.service:answer_question
      ↓
rag/service.py
```

따라서 Chat API가 실행되지만 RAG Function 연결 오류가 발생한다면
`.env`의 `RAG_ANSWER_FUNCTION`을 확인합니다.

---

# 25. Chat API 직접 테스트

Frontend를 제외하고 Backend + RAG만 테스트:

```bash
curl -i \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{"announcementId":1,"question":"신청 일정은 언제인가?"}'
```

---

# 26. Chat 테스트 결과 해석

## HTTP 200 + 정상 Answer

```text
Backend 정상
RAG 정상
Generation 정상
```

이후 화면 문제가 있다면 Frontend를 확인합니다.

---

## HTTP 200 + Evidence 정상 + fallback Answer

예:

```text
공고문 근거는 확인되었지만 현재 답변 생성 품질이 안정적이지 않아...
```

이 경우:

```text
API 연결 성공
Retrieval 성공 가능성 높음
Generation 실패 또는 품질 검증 실패 가능
```

즉 Frontend 연결 문제로 판단하지 않습니다.

---

## HTTP 500

확인:

```text
Backend Log
RAG Exception
DB
Embedding Model
LLM
```

---

## HTTP 422

확인:

```text
announcementId
question
JSON 형식
Content-Type
```

---

# 27. Grounded

Chat Response에는:

```text
grounded
```

Field가 존재합니다.

예:

```json
{
  "grounded": true
}
```

이는 공고문 근거 기반 응답 여부를 Frontend에 전달하기 위한 API 정보입니다.

구체적인 판정 Logic은 RAG 구현을 확인합니다.

---

# 28. Admin Authentication API

Route:

```text
backend/app/api/routes/admin_auth.py
```

Service:

```text
backend/app/services/admin_auth_service.py
```

Schema:

```text
backend/app/schemas/admin_auth.py
```

Frontend:

```text
frontend/admin/js/auth.js
frontend/admin/js/guard.js
```

---

# 29. Admin Auth Endpoint

현재 Route 코드에서 다음 종류의 Endpoint가 존재합니다.

```text
POST
GET
POST
```

구체적인 Path의 최종 기준은:

```text
backend/app/api/routes/admin_auth.py
```

입니다.

Frontend 코드에서 현재 확인되는 호출:

```text
/admin/auth/login
/admin/auth/me
/admin/auth/logout
```

API Base `/api`를 포함하면:

```text
POST /api/admin/auth/login
GET  /api/admin/auth/me
POST /api/admin/auth/logout
```

구조로 사용됩니다.

---

# 30. Admin Login Request

Frontend:

```text
frontend/admin/js/auth.js
```

Backend Schema:

```text
backend/app/schemas/admin_auth.py
```

현재 주요 Field:

```text
admin_id
password
```

Schema 제한:

```text
admin_id
→ 최소 1
→ 최대 100

password
→ 최소 1
→ 최대 200
```

---

# 31. Admin 인증 환경변수

`admin_auth_service.py`에서 현재 사용하는 주요 환경변수:

```text
ADMIN_ID
ADMIN_PASSWORD
ADMIN_JWT_SECRET
ADMIN_JWT_EXPIRE_SECONDS
ADMIN_COOKIE_SECURE
ADMIN_COOKIE_NAME
ADMIN_COOKIE_SAMESITE
```

실제 Secret 값은 문서에 기록하지 않습니다.

---

# 32. Admin API

Route:

```text
backend/app/api/routes/admin.py
```

Service:

```text
backend/app/services/admin_service.py
```

Schema:

```text
backend/app/schemas/admin.py
```

Frontend:

```text
frontend/admin/
```

---

# 33. Admin API 역할

현재 Admin Route는 여러 Endpoint를 포함합니다.

코드 구조상 다음 기능군을 담당합니다.

```text
공고 관리
문서 관리
처리 상태 확인
오류 관리
Pipeline 관련 관리
다운로드
```

실제 Endpoint Path와 Method는:

```text
backend/app/api/routes/admin.py
```

를 최종 기준으로 확인합니다.

---

# 34. Document Download

현재 확인된 Route:

```text
GET /documents/{document_id}/download
```

Admin Router Prefix가 적용되므로 실제 전체 URL은
Router 설정을 함께 확인해야 합니다.

예상 구조를 문서만 보고 확정하지 말고:

```text
backend/app/api/router.py
backend/app/api/routes/admin.py
```

두 파일을 같이 확인합니다.

---

# 35. Error Status Update

Admin Schema에는 Error 상태 변경용으로 다음 값이 확인됩니다.

```text
open
in_progress
resolved
```

즉 Status는 임의 문자열이 아니라 Schema Pattern의 제한을 받습니다.

---

# 36. Pipeline Gateway

파일:

```text
backend/app/services/pipeline_gateway.py
```

역할:

```text
Backend Admin API
      ↓
Pipeline Function
```

환경변수를 통해 Pipeline Function을 연결하는 구조를 사용합니다.

따라서 Admin에서 Pipeline 실행이 실패할 경우:

```text
Route
Service
pipeline_gateway.py
환경변수
실제 Pipeline Function
```

순서로 확인합니다.

---

# 37. Pipeline Persistence

파일:

```text
backend/app/services/pipeline_persistence.py
```

Pipeline 처리 결과를 DB 구조와 연결하는 역할을 담당합니다.

개념:

```text
Pipeline Output
      ↓
Persistence
      ↓
PostgreSQL
```

---

# 38. API Base URL

User Frontend:

```text
frontend/user/src/config.ts
```

현재:

```typescript
export const API_BASE_URL = "/api";
```

Admin Frontend:

```text
frontend/admin/js/config.js
```

현재:

```text
/api
```

---

# 39. Backend Port

현재 개발 기준 Backend:

```text
127.0.0.1:8000
```

Frontend에서는 이 주소를 직접 사용하는 것이 아니라:

```text
/api
```

를 통해 Proxy합니다.

---

# 40. User Frontend API 연결

```text
Browser
 ↓
Vite :5173
 ↓
/api
 ↓
Vite Proxy
 ↓
FastAPI :8000
```

---

# 41. Admin Frontend API 연결

```text
Browser
 ↓
serve_admin.py
 ↓
/api
 ↓
Admin Proxy
 ↓
FastAPI :8000
```

---

# 42. API 디버깅 기본 순서

화면에서 문제가 발생하면:

```text
1. API 직접 curl
2. HTTP Status 확인
3. Response JSON 확인
4. Backend Log 확인
5. Route 확인
6. Schema 확인
7. Service 확인
8. DB/RAG 확인
9. 마지막으로 Frontend 확인
```

API Response 자체가 틀렸는데 Frontend부터 수정하지 않습니다.

---

# 43. HTTP Status 해석

| Status | 의미 |
|---|---|
| `200` | 요청 성공 |
| `400` | 잘못된 요청 가능 |
| `401` | 인증 필요/실패 |
| `403` | 권한 문제 |
| `404` | Route 또는 Resource 없음 |
| `422` | Pydantic Validation 실패 |
| `500` | Backend 내부 오류 |

---

# 44. API Contract 변경 규칙

API를 변경할 때 다음 순서로 확인합니다.

```text
Schema
↓
Route
↓
Service
↓
Frontend
↓
문서
```

예를 들어:

```text
announcementId
```

를:

```text
announcement_id
```

로 Frontend까지 변경하고 싶다면
Backend Schema Alias와 Frontend Request를 함께 변경해야 합니다.

---

# 45. API에서 하지 말아야 할 것

Frontend 편의를 위해 Backend 내부 구조를 그대로 노출하지 않습니다.

예:

```text
SQLAlchemy Object
Raw DB Row
Embedding Vector 전체
Internal File Path
Secret
Password
JWT Secret
```

API Response에는 필요한 정보만 반환합니다.

---

# 46. Chat API의 중요한 경계

Frontend는:

```text
answer
grounded
evidence
```

만 알면 됩니다.

Frontend가 다음을 알 필요는 없습니다.

```text
BGE-M3
pgvector SQL
ChunkSet
Embedding Dimension
LLM Process
Prompt
```

이 구조를 유지해야 RAG 내부 구현을 변경하기 쉽습니다.

---

# 47. Announcement API의 중요한 경계

Frontend는 공고 정보만 받습니다.

```text
Frontend
  ↓
Announcement API
  ↓
Service
  ↓
DB
```

Frontend에서 직접 DB Query를 구현하지 않습니다.

---

# 48. Source of Truth

API 구현 확인 우선순위:

```text
1. backend/app/api/routes/
2. backend/app/schemas/
3. backend/app/services/
4. frontend API 호출 코드
5. docs/API.md
```

문서와 코드가 다르면:

```text
실행 코드
```

가 최종 기준입니다.

그 후 문서를 현재 코드에 맞게 수정합니다.

---

# 49. API 수정 시 확인 파일

## Announcement

```text
backend/app/api/routes/announcements.py
backend/app/schemas/announcement.py
backend/app/services/announcement_service.py

frontend/user/src/components/screens/ListScreen.tsx
frontend/user/src/components/screens/DetailScreen.tsx
```

---

## Chat

```text
backend/app/api/routes/chat.py
backend/app/schemas/chat.py
backend/app/services/chat_service.py

rag/service.py

frontend/user/src/components/screens/DetailScreen.tsx
```

---

## Admin

```text
backend/app/api/routes/admin.py
backend/app/schemas/admin.py
backend/app/services/admin_service.py

frontend/admin/js/
```

---

## Admin Auth

```text
backend/app/api/routes/admin_auth.py
backend/app/schemas/admin_auth.py
backend/app/services/admin_auth_service.py

frontend/admin/js/auth.js
frontend/admin/js/guard.js
```

---

# 50. API Quick Reference

| 기능 | Method | Path |
|---|---|---|
| Backend 상태 | GET | `/api/health` |
| DB 상태 | GET | `/api/health/db` |
| 공고 목록 | GET | `/api/announcements` |
| 공고 상세 | GET | `/api/announcements/{id}` |
| Chat | POST | `/api/chat` |
| 관리자 로그인 | POST | `/api/admin/auth/login` |
| 관리자 인증 확인 | GET | `/api/admin/auth/me` |
| 관리자 로그아웃 | POST | `/api/admin/auth/logout` |

Admin의 나머지 세부 Endpoint는:

```text
backend/app/api/routes/admin.py
```

를 확인합니다.

---

# 51. Chat Quick Test

```bash
cd /home/ubuntu/ddokbot/one-cycle

curl -i \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{
  "announcementId": 1,
  "question": "신청 일정은 언제인가?"
}'
```

---

# 52. Announcement Quick Test

```bash
curl -i \
http://127.0.0.1:8000/api/announcements
```

상세:

```bash
curl -i \
http://127.0.0.1:8000/api/announcements/1
```

---

# 53. Health Quick Test

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

# 54. AI에게 API 오류를 맡길 때

다음 정보를 같이 전달하면 빠르게 분석할 수 있습니다.

```text
docs/API.md

문제가 발생한 curl 명령
HTTP Status
Response JSON
Backend Log

관련 Route
관련 Schema
관련 Service
```

Chat 문제라면 추가:

```text
docs/RAG.md
rag/service.py
rag/db_pipeline.py
```

---

# 55. AI에게 전달할 API 문제 예시

```text
POST /api/chat 호출 시 HTTP 200은 나오지만
answer가 fallback 문장으로 반환된다.

evidence에는 신청 일정 Chunk가 정상적으로 검색된다.

Frontend 문제인지 Backend/RAG 문제인지 분석하고,
API 계약은 변경하지 않는 방향으로 수정해라.
```

이 경우 AI는:

```text
Frontend
```

보다 먼저:

```text
chat.py
↓
chat_service.py
↓
rag/service.py
↓
db_pipeline.py
↓
generation/
```

을 확인해야 합니다.

---

# 56. 핵심 원칙

DDOKBOT API의 역할은:

```text
Frontend와 내부 시스템 사이의 안정적인 계약
```

입니다.

내부 구현:

```text
DB Schema
Pipeline
Embedding
Retrieval
Generation
```

이 변경되더라도 가능하면 API 계약:

```text
URL
Method
Request
Response
```

은 유지합니다.

---

# 57. 전체 API 연결 요약

```text
User Frontend
      │
      ├── GET /api/announcements
      ├── GET /api/announcements/{id}
      └── POST /api/chat
                 │
                 ▼
              FastAPI
                 │
                 ├── Announcement Service → PostgreSQL
                 │
                 └── Chat Service
                         ↓
                     RAG Service
                         ↓
                     DBRAGPipeline
                         ↓
                 PostgreSQL + pgvector
                         ↓
                     Generation
```

Admin:

```text
Admin Frontend
      ↓
/api/admin/*
      ↓
FastAPI
      ↓
Admin Service
      ├── PostgreSQL
      └── Pipeline Gateway
```

이 구조를 API 개발 및 디버깅의 기본 기준으로 사용합니다.
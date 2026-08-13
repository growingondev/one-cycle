# DDOKBOT Frontend

> 이 문서는 DDOKBOT의 사용자 Frontend와 관리자 Frontend 구조를 설명합니다.
>
> 새로운 개발자 또는 AI가 다음 내용을 이해할 수 있도록 작성되었습니다.
>
> - 사용자 Frontend가 어디에 있는지
> - React/Vite가 어떻게 실행되는지
> - `/api` 요청이 Backend로 어떻게 전달되는지
> - 공고 목록/상세/채팅 화면이 어느 파일에 있는지
> - 관리자 Frontend는 어떤 방식으로 실행되는지
> - Frontend 문제가 발생했을 때 어느 계층부터 확인해야 하는지
> - AWS 서버의 Frontend를 로컬 Browser에서 어떻게 확인하는지

---

# 1. Frontend 전체 구조

DDOKBOT Frontend는 두 개의 UI로 나뉩니다.

```text
frontend/
├── user/
└── admin/
```

역할:

```text
frontend/user/
→ 일반 사용자 서비스

frontend/admin/
→ 관리자 서비스
```

두 Frontend는 구현 방식이 서로 다릅니다.

---

# 2. User Frontend Stack

경로:

```text
frontend/user/
```

현재 기술:

```text
React
TypeScript
Vite
Tailwind CSS
```

Package 관리:

```text
frontend/user/package.json
frontend/user/package-lock.json
```

---

# 3. User Frontend 기본 구조

```text
frontend/user/
├── index.html
├── package.json
├── package-lock.json
├── postcss.config.js
├── tailwind.config.js
├── tsconfig.json
├── vite.config.ts
│
├── public/
│   └── image.png
│
└── src/
    ├── App.tsx
    ├── config.ts
    ├── index.css
    ├── main.tsx
    └── components/
        └── screens/
```

실제 화면별 Component는:

```text
frontend/user/src/components/screens/
```

에 위치합니다.

---

# 4. User Frontend Entry

React Entry:

```text
frontend/user/src/main.tsx
```

Application Root Component:

```text
frontend/user/src/App.tsx
```

개념:

```text
index.html
   ↓
main.tsx
   ↓
App.tsx
   ↓
각 Screen Component
```

---

# 5. App.tsx

파일:

```text
frontend/user/src/App.tsx
```

역할:

```text
전체 Screen 전환
선택된 공고 상태 관리
Toast 관리
상위 UI Flow 관리
```

현재 주요 Screen 개념:

```text
intro
list
detail
guide
glossary
```

Admin UI는 별도 `frontend/admin/` 프로젝트이므로
사용자 React UI에 관리자 기능을 다시 구현하지 않습니다.

---

# 6. Frontend API 설정

User Frontend의 API Base 설정:

```text
frontend/user/src/config.ts
```

현재:

```typescript
export const API_BASE_URL = "/api";
```

이 파일을 API Base URL의 단일 Source of Truth로 사용합니다.

즉 다른 Component에 다음처럼 Backend 주소를 직접 하드코딩하지 않습니다.

```text
http://127.0.0.1:8000
```

또는:

```text
http://AWS_PUBLIC_IP:8000
```

대신:

```text
/api
```

를 사용합니다.

---

# 7. API Base를 하나로 관리하는 이유

잘못된 구조:

```text
ListScreen.tsx
→ http://127.0.0.1:8000/api

DetailScreen.tsx
→ http://52.xxx.xxx.xxx:8000/api

다른 Component
→ /api
```

이런 식으로 분산되면 환경이 바뀔 때 전체 코드를 수정해야 합니다.

현재 권장 구조:

```text
src/config.ts
      ↓
API_BASE_URL
      ↓
모든 API Component
```

---

# 8. Vite Proxy

파일:

```text
frontend/user/vite.config.ts
```

User Frontend Browser는 Backend에 직접 연결하지 않고
Vite 개발 서버의 `/api`를 사용합니다.

개념:

```text
Browser
   ↓
http://127.0.0.1:5173
   ↓
/api/*
   ↓
Vite Proxy
   ↓
http://127.0.0.1:8000/api/*
   ↓
FastAPI
```

따라서 개발 환경에서는 Browser 입장에서 Frontend와 API가 같은 Origin처럼 보이게 할 수 있습니다.

실제 Proxy 설정 값의 최종 기준은:

```text
frontend/user/vite.config.ts
```

입니다.

---

# 9. User Frontend 실행

AWS 서버에서:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run dev
```

`package.json`의 현재 개발 Script:

```text
vite --host 0.0.0.0
```

일반적인 Vite 개발 Port:

```text
5173
```

실제 실행 시 Terminal에 출력되는 URL을 최종 기준으로 확인합니다.

---

# 10. User Frontend Production Build

Frontend 코드 변경 후 반드시 Build를 확인합니다.

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run build
```

정상 예:

```text
vite building...
modules transformed
dist/index.html
dist/assets/...
✓ built
```

현재 프로젝트 정리 후 User Frontend Production Build 성공이 확인되었습니다.

---

# 11. Build Output

Production Build 결과:

```text
frontend/user/dist/
```

이 디렉터리는 Source Code가 아니라 Build Artifact입니다.

Source of Truth:

```text
frontend/user/src/
```

입니다.

---

# 12. 공고 목록 화면

파일:

```text
frontend/user/src/components/screens/ListScreen.tsx
```

역할:

```text
공고 목록 조회
검색
지역 필터
상태 필터
정렬
Pagination
공고 선택
```

Backend API:

```text
GET /api/announcements
```

호출 구조:

```text
ListScreen.tsx
       ↓
API_BASE_URL
       ↓
/api/announcements
       ↓
Vite Proxy
       ↓
FastAPI
```

---

# 13. ListScreen API 코드 구조

개념:

```typescript
fetch(`${API_BASE_URL}/announcements`)
```

응답 성공 후:

```text
data.items
```

를 공고 목록으로 사용합니다.

따라서 목록이 안 보일 때:

```text
Frontend Rendering 문제
```

라고 바로 판단하지 않습니다.

먼저 API Response를 확인합니다.

---

# 14. 공고 목록 문제 진단

순서:

```text
1. Backend가 실행 중인가?
2. GET /api/announcements가 curl에서 정상인가?
3. Vite Proxy가 정상인가?
4. Browser Network에서 요청이 성공하는가?
5. data.items가 존재하는가?
6. ListScreen 렌더링이 정상인가?
```

Backend 직접 확인:

```bash
curl -i \
http://127.0.0.1:8000/api/announcements
```

---

# 15. ListScreen 관련 주의사항

이전에 다음 오타가 존재했습니다.

```text
API_BASE_UR
```

정상 값:

```text
API_BASE_URL
```

현재 수정 후 Frontend Build 성공이 확인되었습니다.

API 관련 변수명을 변경할 경우 TypeScript Build를 반드시 실행합니다.

---

# 16. 공고 상세 화면

파일:

```text
frontend/user/src/components/screens/DetailScreen.tsx
```

역할:

```text
선택 공고 상세 조회
공고 정보 표시
Chat UI
Evidence 표시
입력 관리
사용자/AI 메시지 관리
```

---

# 17. 공고 상세 API

DetailScreen에서:

```text
GET /api/announcements/{id}
```

를 호출합니다.

개념:

```typescript
fetch(
  `${API_BASE_URL}/announcements/${notice.id}`
)
```

전체 흐름:

```text
ListScreen
    ↓
사용자가 공고 선택
    ↓
App
    ↓
DetailScreen
    ↓
GET /api/announcements/{id}
    ↓
FastAPI
```

---

# 18. Chat UI

Chat 역시:

```text
DetailScreen.tsx
```

에서 처리합니다.

사용자가 질문 입력:

```text
신청 일정은 언제인가?
```

전송:

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

# 19. Chat Frontend Flow

```text
사용자 입력
   ↓
DetailScreen.send()
   ↓
User Message 추가
   ↓
POST /api/chat
   ↓
Backend
   ↓
RAG
   ↓
JSON Response
   ↓
AI Message 추가
```

---

# 20. Chat Response

Backend 주요 Response:

```json
{
  "answer": "...",
  "grounded": true,
  "evidence": []
}
```

Frontend는:

```text
data.answer
```

를 AI 메시지 Text로 사용합니다.

그리고:

```text
data.evidence
```

가 Array이면 Evidence로 저장합니다.

---

# 21. Frontend와 RAG의 경계

Frontend는 다음 내용을 알 필요가 없습니다.

```text
BGE-M3
pgvector
ChunkSet
ProcessingRun
LLM Prompt
llama.cpp
```

Frontend가 알아야 하는 것은 API Contract뿐입니다.

```text
POST /api/chat

Input:
announcementId
question

Output:
answer
grounded
evidence
```

RAG 구현이 변경되어도 이 API Contract를 유지하는 것이 중요합니다.

---

# 22. Chat 오류 처리

Chat API Response가 HTTP 오류인 경우:

```text
response.ok == false
```

이면 Frontend에서 Error를 발생시킵니다.

즉 다음은 다른 문제입니다.

```text
HTTP 500
→ Backend/RAG 오류

HTTP 200 + fallback answer
→ Backend 연결은 성공
→ RAG Generation 품질 문제 가능

HTTP 200 + 정상 answer
→ 전체 연결 정상
```

---

# 23. Evidence

ChatResponse에는 검색 근거가 포함될 수 있습니다.

예:

```json
{
  "chunkId": "...",
  "sectionTitle": "...",
  "content": "...",
  "score": 0.58
}
```

Frontend에서는 Evidence를 사용자에게 근거 확인 UI로 보여줄 수 있습니다.

---

# 24. Frontend에서 Answer가 이상할 때

예:

```text
공고문 근거는 확인되었지만 현재 답변 생성 품질이 안정적이지 않아...
```

가 화면에 나왔다면 Frontend가 해당 문자열을 만든 것이 아닐 수 있습니다.

먼저 API를 직접 확인합니다.

```bash
curl -i \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{"announcementId":1,"question":"신청 일정은 언제인가?"}'
```

curl에도 같은 Answer가 나오면:

```text
Frontend 문제 X
Backend/RAG 문제
```

입니다.

---

# 25. User Frontend 문제 분류

## 화면 자체가 열리지 않음

확인:

```text
npm run dev
Vite Port
SSH Forwarding
Browser URL
```

---

## 화면은 열리지만 공고가 없음

확인:

```text
GET /api/announcements
Vite Proxy
ListScreen
```

---

## 공고 상세가 안 열림

확인:

```text
GET /api/announcements/{id}
DetailScreen
notice.id
```

---

## Chat 자체가 실패

확인:

```text
POST /api/chat
Backend log
RAG
```

---

## Chat 응답은 오는데 내용만 이상함

확인:

```text
RAG Retrieval
RAG Generation
```

Frontend부터 수정하지 않습니다.

---

# 26. User Frontend Build 문제

Build:

```bash
npm run build
```

오류가 발생하면 다음을 확인합니다.

```text
TypeScript 변수명
잘못된 Import
잘못된 Component Path
사용하지 않는/존재하지 않는 Export
문법 오류
```

특히 API 변수 오타는 Build로 빠르게 발견할 수 있습니다.

---

# 27. User Frontend API Source of Truth

API Base:

```text
frontend/user/src/config.ts
```

API Contract:

```text
docs/API.md
backend/app/schemas/
backend/app/api/routes/
```

화면:

```text
frontend/user/src/components/screens/
```

Proxy:

```text
frontend/user/vite.config.ts
```

---

# 28. AWS 서버의 User Frontend를 로컬에서 보는 방법

AWS 서버 내부에서 Vite가:

```text
127.0.0.1:5173
```

또는:

```text
0.0.0.0:5173
```

에 실행 중이라고 가정합니다.

로컬 Mac Terminal에서 SSH Port Forwarding을 사용합니다.

```bash
ssh -i <PEM_FILE_PATH> \
-L 5173:127.0.0.1:5173 \
ubuntu@<AWS_PUBLIC_IP>
```

예시의 `<PEM_FILE_PATH>`와 `<AWS_PUBLIC_IP>`는 실제 환경에 맞게 입력합니다.

---

# 29. PEM 파일 관련 주의

다음 오류:

```text
Warning: Identity file ... not accessible
Permission denied (publickey)
```

가 나오면 Frontend 문제가 아닙니다.

로컬 Terminal이 PEM 파일을 찾지 못한 것입니다.

확인:

```bash
ls -l <PEM_FILE_PATH>
```

PEM의 실제 위치를 SSH 명령에 지정합니다.

---

# 30. 로컬 Browser 접근

SSH Tunnel 연결 후 일반적으로:

```text
http://127.0.0.1:5173
```

또는:

```text
http://localhost:5173
```

으로 접근합니다.

---

# 31. Backend Port Forwarding은 항상 필요한가

User Frontend 개발 환경에서 Vite Proxy가:

```text
/api
→ FastAPI :8000
```

으로 연결되어 있고 두 Server가 같은 AWS 서버 안에 있다면,
Browser가 Backend `8000` 포트에 직접 접근할 필요는 없습니다.

개념:

```text
Local Browser
      ↓
SSH 5173 Tunnel
      ↓
AWS Vite :5173
      ↓
AWS localhost:8000
      ↓
FastAPI
```

따라서 User Frontend 확인만 목적이라면 5173 Forwarding만으로도 동작할 수 있습니다.

---

# 32. Backend를 직접 로컬에서 호출해야 할 경우

필요하면 별도의 Forwarding을 추가할 수 있습니다.

예:

```bash
ssh -i <PEM_FILE_PATH> \
-L 5173:127.0.0.1:5173 \
-L 8000:127.0.0.1:8000 \
ubuntu@<AWS_PUBLIC_IP>
```

이 경우 로컬에서:

```text
http://127.0.0.1:8000
```

으로 Backend를 직접 확인할 수 있습니다.

---

# 33. Admin Frontend

경로:

```text
frontend/admin/
```

User Frontend와 달리 React/Vite 기반이 아닙니다.

구성:

```text
HTML
CSS
JavaScript
Python Static/Proxy Server
```

---

# 34. Admin Frontend 구조

```text
frontend/admin/
├── announcement.html
├── document.html
├── error.html
├── login.html
│
├── components/
│   ├── header.html
│   ├── modal.html
│   ├── pagination.html
│   └── sidebar.html
│
├── css/
│
├── js/
│
└── serve_admin.py
```

---

# 35. Admin JavaScript

주요 파일:

```text
frontend/admin/js/
```

확인된 주요 역할:

```text
api.js
→ 공통 API 요청

auth.js
→ 관리자 인증

config.js
→ API Base 설정

announcement.js
→ 공고 관리

document.js
→ 문서 관리

error.js
→ 오류 관리

guard.js
→ 인증 Guard

token.js
→ Token 관련 처리

common.js
→ 공통 UI
```

---

# 36. Admin API Base

파일:

```text
frontend/admin/js/config.js
```

현재 API Base:

```text
/api
```

개념:

```text
Admin JS
  ↓
/api
  ↓
serve_admin.py
  ↓
FastAPI :8000
```

---

# 37. Admin Static/Proxy Server

파일:

```text
frontend/admin/serve_admin.py
```

역할:

```text
1. Admin HTML/CSS/JS 제공
2. /api 요청을 FastAPI로 Proxy
```

개념:

```text
Browser
  ↓
Admin Server
  ├── HTML/CSS/JS
  │
  └── /api/*
          ↓
       FastAPI
```

---

# 38. Admin Backend Target

현재 프로젝트 정리 이후 Backend 개발 Port는:

```text
8000
```

을 기준으로 사용합니다.

Admin Server 코드에서 API Target의 최종 기준은:

```text
frontend/admin/serve_admin.py
```

입니다.

과거 문서나 코드에:

```text
18000
```

이 남아 있다면 현재 Runtime과 일치하는지 반드시 확인합니다.

---

# 39. Admin Frontend 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/admin

python serve_admin.py
```

실제 지원 옵션 확인:

```bash
python serve_admin.py --help
```

가장 정확합니다.

---

# 40. User와 Admin Frontend 차이

| 구분 | User | Admin |
|---|---|---|
| 경로 | `frontend/user` | `frontend/admin` |
| Framework | React | Static HTML/JS |
| Language | TypeScript | JavaScript |
| Dev Server | Vite | `serve_admin.py` |
| API Base | `/api` | `/api` |
| Backend | FastAPI :8000 | FastAPI :8000 |
| 주요 목적 | 사용자 조회/Chat | 운영/관리 |

---

# 41. Frontend에서 Backend 직접 구현 금지

Frontend 코드에 다음 Logic을 넣지 않습니다.

```text
SQL Query
pgvector
RAG Retrieval
Pipeline 실행
DB Password
Admin Secret
```

항상:

```text
Frontend
  ↓
Backend API
```

를 통해 처리합니다.

---

# 42. Frontend 변경 시 API Contract 유지

화면 디자인이나 Component 구조를 대폭 변경해도 가능하면 다음은 유지합니다.

```text
GET /api/announcements
GET /api/announcements/{id}
POST /api/chat
```

Backend와 Frontend를 동시에 갈아엎지 않도록 하기 위한 원칙입니다.

---

# 43. Backend 변경 시 Frontend 보호

Backend 내부 구현을 변경하더라도:

```text
URL
HTTP Method
Request Field
Response Field
```

를 유지하면 Frontend는 대부분 수정하지 않아도 됩니다.

예:

```json
{
  "answer": "...",
  "grounded": true,
  "evidence": []
}
```

계약을 유지합니다.

---

# 44. Frontend Smoke Test

코드 수정 후 최소 확인:

```text
1. npm run build
2. npm run dev
3. Intro 화면
4. 공고 목록
5. 공고 상세
6. Chat 전송
7. Chat Answer 표시
8. Evidence 표시
```

---

# 45. API가 정상인지 먼저 확인

Frontend 문제를 진단하기 전에 Backend 직접 테스트:

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

# 46. Browser Developer Tools

Frontend가 이상할 때 Browser Developer Tools에서:

```text
Console
Network
```

를 확인합니다.

Network에서:

```text
Request URL
Status
Request Payload
Response
```

를 확인합니다.

---

# 47. Network Status별 판단

## 200

Backend 응답 성공.

Response 내용 확인.

---

## 404

```text
잘못된 API URL
Proxy 문제
Route 문제
```

---

## 422

```text
Request JSON Schema 불일치
```

확인:

```text
announcementId
question
```

---

## 500

```text
Backend 내부 오류
```

Browser Console보다 Backend Terminal Traceback이 중요합니다.

---

## Failed to fetch

가능성:

```text
Vite Proxy
Server Down
잘못된 Host
Network
Port Forwarding
```

---

# 48. User Frontend 수정 위치 Quick Reference

| 기능 | 위치 |
|---|---|
| 전체 Screen Flow | `src/App.tsx` |
| API Base | `src/config.ts` |
| 공고 목록 | `src/components/screens/ListScreen.tsx` |
| 공고 상세 | `src/components/screens/DetailScreen.tsx` |
| Chat | `src/components/screens/DetailScreen.tsx` |
| Global CSS | `src/index.css` |
| Vite Proxy | `vite.config.ts` |
| Package | `package.json` |

---

# 49. Admin Frontend 수정 위치 Quick Reference

| 기능 | 위치 |
|---|---|
| 로그인 | `login.html`, `js/auth.js` |
| 공고 관리 | `announcement.html`, `js/announcement.js` |
| 문서 관리 | `document.html`, `js/document.js` |
| 오류 관리 | `error.html`, `js/error.js` |
| 공통 API | `js/api.js` |
| API Base | `js/config.js` |
| Auth Guard | `js/guard.js` |
| 공통 Header/Sidebar | `components/` |
| Proxy Server | `serve_admin.py` |

---

# 50. Frontend 파일을 이동할 때

Component를 이동하면 Import Path를 반드시 확인합니다.

예:

```text
src/components/screens/ListScreen.tsx
```

를 이동하면:

```text
App.tsx
다른 Screen
config import
CSS import
```

등을 함께 검사합니다.

이후 반드시:

```bash
npm run build
```

를 실행합니다.

---

# 51. Source of Truth

| 영역 | Source of Truth |
|---|---|
| User Entry | `frontend/user/src/main.tsx` |
| User App | `frontend/user/src/App.tsx` |
| User API Base | `frontend/user/src/config.ts` |
| User Screens | `frontend/user/src/components/screens/` |
| Vite Config | `frontend/user/vite.config.ts` |
| User Dependencies | `frontend/user/package.json` |
| Admin API Config | `frontend/admin/js/config.js` |
| Admin API Client | `frontend/admin/js/api.js` |
| Admin Auth | `frontend/admin/js/auth.js` |
| Admin Proxy | `frontend/admin/serve_admin.py` |
| Backend API Contract | `backend/app/api/routes/`, `backend/app/schemas/` |

---

# 52. AI에게 User Frontend 작업을 맡길 때

최소 전달:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/FRONTEND.md
docs/API.md

frontend/user/
```

Backend 연동 문제면 추가:

```text
backend/app/api/routes/
backend/app/schemas/
```

Chat 문제면 추가:

```text
docs/RAG.md
backend/app/api/routes/chat.py
backend/app/schemas/chat.py
rag/service.py
```

---

# 53. AI에게 Admin Frontend 작업을 맡길 때

최소:

```text
README.md
docs/ARCHITECTURE.md
docs/FRONTEND.md
docs/API.md

frontend/admin/

backend/app/api/routes/admin.py
backend/app/api/routes/admin_auth.py
backend/app/schemas/admin.py
backend/app/schemas/admin_auth.py
```

---

# 54. AI가 Frontend 수정 전 확인할 질문

```text
1. User Frontend인가 Admin Frontend인가?
2. API는 curl에서 정상인가?
3. Browser Network Status는 무엇인가?
4. API Base는 /api인가?
5. Vite/Admin Proxy는 정상인가?
6. Request Field가 Backend Schema와 맞는가?
7. Response Field가 Frontend 코드와 맞는가?
8. UI 문제인가 API 문제인가?
```

---

# 55. User Frontend 전체 연결

```text
Browser
   ↓
Vite
   ↓
React App
   ↓
ListScreen / DetailScreen
   ↓
API_BASE_URL = /api
   ↓
Vite Proxy
   ↓
FastAPI :8000
   ↓
Service
   ↓
DB / RAG
```

---

# 56. Admin Frontend 전체 연결

```text
Browser
   ↓
serve_admin.py
   ↓
HTML / CSS / JS
   ↓
/api
   ↓
serve_admin.py Proxy
   ↓
FastAPI :8000
   ↓
Admin Service
   ↓
DB / Pipeline
```

---

# 57. 가장 중요한 디버깅 원칙

Frontend 화면에서 문제가 보인다고 해서
항상 Frontend 문제인 것은 아닙니다.

예:

```text
화면에 잘못된 AI 답변 표시
```

먼저:

```text
POST /api/chat Response
```

를 확인합니다.

Response 자체가 잘못되었다면:

```text
RAG/Backend 문제
```

입니다.

반대로 curl에서는 정상이지만 화면에 표시되지 않는다면:

```text
Frontend 문제
```

입니다.

---

# 58. 핵심 요약

현재 User Frontend의 연결 구조:

```text
React/Vite
   ↓
API_BASE_URL = /api
   ↓
Vite Proxy
   ↓
FastAPI :8000
```

주요 사용자 화면:

```text
ListScreen.tsx
→ 공고 목록

DetailScreen.tsx
→ 공고 상세 + Chat
```

현재 Admin Frontend:

```text
Static HTML/CSS/JS
   ↓
serve_admin.py
   ↓
/api Proxy
   ↓
FastAPI :8000
```

Frontend 관련 문제를 수정할 때는 반드시 먼저:

```text
API가 정상인지
```

확인합니다.

API가 정상이라면 Frontend를 보고,
API 자체가 잘못되었다면 Backend/RAG를 먼저 수정합니다.
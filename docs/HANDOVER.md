# DDOKBOT Handover Guide

> 이 문서는 DDOKBOT 프로젝트 인수인계용 문서입니다.
>
> 목적:
>
> - 현재 프로젝트가 어디까지 구현되었는지
> - 어떤 기능이 실제로 동작하는지
> - 어떤 부분이 아직 불안정한지
> - 다음 작업 우선순위가 무엇인지
> - 새 개발자나 AI가 어떤 문서를 먼저 읽어야 하는지
> - 어떤 코드는 건드리면 안 되는지
> - 어떤 검증을 다시 해야 하는지
>
> 이 문서는 "현재 상태 요약"이므로
> 구조가 크게 변경되거나 기능이 완료되면 반드시 갱신합니다.

---

# 1. Project Root

```text
/home/ubuntu/ddokbot/one-cycle
```

---

# 2. 문서 읽는 순서

새 개발자 또는 AI는 아래 순서로 읽습니다.

```text
1. README.md
2. docs/HANDOVER.md
3. docs/ARCHITECTURE.md
4. docs/PROJECT_STRUCTURE.md
5. 작업 영역별 세부 문서
```

세부 문서:

```text
docs/PIPELINE.md
docs/RAG.md
docs/DATABASE.md
docs/BACKEND.md
docs/FRONTEND.md
docs/API.md
docs/ENVIRONMENT.md
docs/DEVELOPMENT.md
docs/TROUBLESHOOTING.md
```

---

# 3. 현재 프로젝트 목표

DDOKBOT은 LH 공고문 기반 질의응답 서비스를 목표로 합니다.

핵심 흐름:

```text
HWP / HWPX
    ↓
Parser
    ↓
Normalizer
    ↓
Structure
    ↓
Chunking
    ↓
Embedding
    ↓
PostgreSQL + pgvector
    ↓
Runtime Retrieval
    ↓
LLM Generation
    ↓
FastAPI
    ↓
Frontend
```

---

# 4. 현재 완료된 영역

현재까지 확인된 완료/동작 영역:

```text
[완료] HWP/HWPX Parser
[완료] Normalizer
[완료] Structure Pipeline
[완료] Chunking
[완료] BGE-M3 Embedding
[완료] PostgreSQL Persistence
[완료] pgvector 기반 Retrieval
[완료] FastAPI Backend 연결
[완료] 사용자 Frontend 연결
[완료] 공고 목록 API 연결
[완료] 공고 상세 API 연결
[완료] Chat API 연결
[완료] Frontend Production Build
[완료] 프로젝트 폴더 1차 정리
[완료] Legacy RAG 코드 상당 부분 제거
[완료] 주요 프로젝트 문서 작성
```

---

# 5. 현재 동작 확인된 Frontend

사용자 Frontend:

```text
frontend/user/
```

현재 확인된 흐름:

```text
Intro
 ↓
공고 목록
 ↓
공고 상세
 ↓
Chat
```

Frontend와 Backend의 연결 자체는 확인되었습니다.

User Frontend Build도 성공한 상태입니다.

---

# 6. 현재 동작 확인된 API

대표 API:

```text
GET /api/health
GET /api/health/db

GET /api/announcements
GET /api/announcements/{id}

POST /api/chat
```

Chat Request:

```json
{
  "announcementId": 1,
  "question": "신청 일정은 언제인가?"
}
```

---

# 7. 현재 Chat Retrieval 상태

질문 예:

```text
신청 일정은 언제인가?
```

Retrieval 결과에서 실제로 관련 근거가 검색되었습니다.

예:

```text
‘26.07.23.(목) 오전 10시 ~ 별도 공지시까지

운영시간:
10:00~16:00
12:00~13:00 및 주말·공휴일 미운영
```

즉 현재 확인된 상태:

```text
Query Embedding
→ 정상

PostgreSQL Connection
→ 정상

pgvector Retrieval
→ 정상

Evidence 반환
→ 정상
```

---

# 8. 현재 가장 큰 미완료 영역

현재 가장 중요한 미해결 문제는:

```text
Generation 안정성
```

입니다.

특히 llama.cpp에서 사용하는 Qwen 계열 모델이
간헐적 또는 반복적으로 중국어 문장을 섞어 생성하는 문제가 있었습니다.

실제 발생 예:

```text
휴憩时间
这里是中文
```

따라서 현재 RAG 상태를 다음처럼 이해해야 합니다.

```text
Retrieval
→ 상당 부분 정상

Generation
→ 불안정
```

---

# 9. Generation 문제에서 이미 시도한 것

현재까지 시도된 대응:

```text
temperature = 0.0
top_p = 1.0
```

Prompt에:

```text
반드시 한국어로만 작성
중국어/일본어 포함 금지
```

규칙을 추가했습니다.

또한:

```text
validate_korean_answer()
```

를 사용하여 중국어/일본어 문자가 포함된 응답을 감지하는 로직을 추가했습니다.

---

# 10. Generation Validation 문제

중국어 응답을 단순히 차단하면 다음 문제가 발생했습니다.

```text
LLM 응답
 ↓
중국어 포함
 ↓
GenerationError
 ↓
Retry
 ↓
Retry도 중국어 포함
 ↓
GenerationError
 ↓
HTTP 500
```

따라서 단순 Validation만으로는 충분하지 않았습니다.

---

# 11. 현재 Chat API Fallback

API 전체가 500으로 죽지 않도록
Generation 실패 시 Fallback Answer를 반환하는 구조를 적용했습니다.

현재 확인된 Response 예:

```json
{
  "answer": "공고문 근거는 확인되었지만 현재 답변 생성 품질이 안정적이지 않아 정확한 문장으로 제공하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  "grounded": true,
  "evidence": [...]
}
```

즉:

```text
HTTP 200
Retrieval 성공
Evidence 존재
Generation 실패
```

상태를 사용자에게 전달할 수 있습니다.

---

# 12. Generation 문제를 해결할 때 우선 확인할 파일

```text
rag/generation/config.py
rag/generation/context_builder.py
rag/generation/prompt_builder.py
rag/generation/llm_client.py
rag/generation/generator.py
rag/generation/models.py
```

추가:

```text
rag/service.py
rag/db_pipeline.py
```

---

# 13. Generation 문제에서 건드리지 말아야 할 영역

Evidence가 정확한 상태라면
Generation 문제 때문에 다음 영역을 먼저 수정하지 않습니다.

```text
Parser
Normalizer
Structure
Chunking
Embedding
Database
Frontend
```

Retrieval까지 정상임이 확인된 상태에서는
Generation만 먼저 해결합니다.

---

# 14. 현재 Runtime RAG 구조

과거에는 다음 구조가 있었습니다.

```text
BM25
Hybrid Search
RRF
File Corpus
Reranker
```

현재 Runtime은 해당 구조를 사용하지 않습니다.

현재 기준:

```text
Question
 ↓
BGE-M3 Query Embedding
 ↓
PostgreSQL + pgvector
 ↓
Top-K Retrieval
 ↓
Generation
```

Source of Truth:

```text
rag/db_pipeline.py
```

---

# 15. 제거된 Legacy RAG 영역

기존에 존재했던 다음 영역은 현재 Runtime 기준으로 제거되었습니다.

```text
rag/reranker/
BM25 검색
Hybrid Search
RRF Fusion
File Corpus Loader
기존 Vector File Search
```

현재 `rag/` 구조는 다음을 기준으로 유지합니다.

```text
rag/
├── db_pipeline.py
├── models.py
├── service.py
├── generation/
└── retrieval/
```

---

# 16. 현재 Retrieval 구조

현재 Runtime Retrieval:

```text
rag/db_pipeline.py
```

Query Embedding:

```text
rag/retrieval/query_embedding.py
```

Embedding Model Loader:

```text
pipeline/embedding/model_loader.py
```

---

# 17. 현재 Embedding Model

```text
BAAI/bge-m3
```

현재 Vector Dimension:

```text
1024
```

현재 검증된 GPU:

```text
NVIDIA L4
```

---

# 18. Database 핵심 구조

Runtime RAG와 직접 관련된 핵심 관계:

```text
Announcement
    ↓
Document
    ↓
ProcessingRun
    ↓
ChunkSet
    ↓
Chunk
    ↓
Embedding
```

Runtime 검색 대상은 Active 데이터입니다.

```text
ProcessingRun.is_active = TRUE
ChunkSet.is_active = TRUE
```

---

# 19. DB Write와 Activation

중요:

```text
Persistence Write
```

와:

```text
Activation
```

은 별개입니다.

Pipeline 결과를 DB에 저장했다고 해서
새 데이터가 자동으로 Runtime 검색 대상이 되는 것은 아닙니다.

---

# 20. Pipeline 수정 시 주의

Pipeline의 어느 Stage를 수정했는지에 따라
다시 실행해야 하는 범위가 다릅니다.

```text
Parser 수정
→ 이후 전체

Normalizer 수정
→ Normalize 이후 전체

Structure 수정
→ Structure 이후 전체

Chunking 수정
→ Chunk 이후 전체

Embedding 수정
→ Embedding 이후
```

Generation 수정은 Pipeline 재실행이 필요하지 않습니다.

---

# 21. 현재 Frontend 구조

User:

```text
frontend/user/
```

기술:

```text
React
TypeScript
Vite
```

Admin:

```text
frontend/admin/
```

기술:

```text
HTML
CSS
JavaScript
Python Proxy Server
```

---

# 22. User Frontend API Base

Source of Truth:

```text
frontend/user/src/config.ts
```

현재:

```typescript
export const API_BASE_URL = "/api";
```

다른 파일에 Backend 주소를 하드코딩하지 않습니다.

---

# 23. 해결된 Frontend 문제

과거 다음 오타가 있었습니다.

```text
API_BASE_UR
```

정상:

```text
API_BASE_URL
```

수정 후:

```text
npm run build
```

성공을 확인했습니다.

---

# 24. Frontend Build 상태

현재:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user
npm run build
```

성공이 확인되었습니다.

즉 현재 TypeScript/Vite Build 기준으로는
Frontend Source가 정상적으로 Compile됩니다.

---

# 25. Frontend와 Backend 연결

현재 구조:

```text
Browser
 ↓
Vite :5173
 ↓
/api
 ↓
FastAPI :8000
```

로컬 Browser에서 AWS Frontend를 확인할 경우
SSH Port Forwarding을 사용합니다.

---

# 26. 현재 주요 Port

```text
User Frontend
5173

FastAPI
8000

llama.cpp
8080
```

실제 설정은 각 Config 파일을 최종 기준으로 확인합니다.

---

# 27. 관리자 Frontend

Admin Frontend는 현재 다음 구조입니다.

```text
frontend/admin/
├── login.html
├── announcement.html
├── document.html
├── error.html
├── components/
├── css/
├── js/
└── serve_admin.py
```

Admin API는 `/api`를 통해 Backend로 연결됩니다.

---

# 28. 현재 Crawler 상태

현재:

```text
crawler/
└── __init__.py
```

만 존재합니다.

따라서 실제 LH 공고 자동 수집 기능은 아직 구현 완료 상태로 보면 안 됩니다.

현재 Pipeline 입력은 Test Fixture 문서를 중심으로 검증되었습니다.

---

# 29. Test Fixture 위치

```text
tests/fixtures/documents/
```

현재 공고:

```text
announcement_001
announcement_002
announcement_003
announcement_004
```

HWP/HWPX 테스트 원본이 저장되어 있습니다.

---

# 30. 현재 문서 처리 Pipeline

전체 실행 진입점:

```text
run_pipeline.py
```

현재 Pipeline:

```text
Parser
 ↓
Normalizer
 ↓
Structure
 ↓
Chunking
 ↓
Embedding
 ↓
Persistence
```

---

# 31. 현재 공식 문서

```text
README.md

docs/
├── API.md
├── ARCHITECTURE.md
├── BACKEND.md
├── DATABASE.md
├── DEVELOPMENT.md
├── ENVIRONMENT.md
├── FRONTEND.md
├── HANDOVER.md
├── PIPELINE.md
├── PROJECT_STRUCTURE.md
├── RAG.md
└── TROUBLESHOOTING.md
```

과거 README나 임시 Markdown보다 이 문서 세트를 우선 사용합니다.

---

# 32. 새 개발자가 가장 먼저 해야 할 것

다음 명령으로 프로젝트 상태를 확인합니다.

```bash
cd /home/ubuntu/ddokbot/one-cycle

find . \
-maxdepth 3 \
-not -path '*/node_modules/*' \
-not -path '*/__pycache__/*' \
-not -path './outputs/*' \
| sort
```

그 다음:

```bash
find docs \
-maxdepth 1 \
-type f \
-printf '%f\n' \
| sort
```

---

# 33. Python Compile 확인

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m compileall -q \
backend \
config \
pipeline \
rag \
migrations \
run_pipeline.py

echo "EXIT=$?"
```

정상:

```text
EXIT=0
```

---

# 34. Frontend Build 확인

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run build
```

---

# 35. Backend 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle

set -a
source .env
set +a

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m uvicorn backend.app.main:app \
--host 127.0.0.1 \
--port 8000
```

---

# 36. API 기본 검증

Health:

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

DB:

```bash
curl -i \
http://127.0.0.1:8000/api/health/db
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

# 37. 현재 Chat 검증 시 판단 기준

Response에:

```text
evidence
```

가 있고 해당 Evidence가 질문과 정확히 관련된다면:

```text
Retrieval 성공
```

으로 판단합니다.

그 후 Answer를 별도로 확인합니다.

---

# 38. 가장 먼저 해결해야 할 다음 작업

현재 우선순위 1:

```text
Generation 안정화
```

구체적으로:

```text
중국어/일본어 혼입 문제 해결
Generation Validation 전략 개선
Fallback 의존도 감소
Prompt 개선
LLM Runtime/Model 검토
```

---

# 39. Generation 안정화 작업 순서 권장

```text
1. Raw LLM Response 저장/확인
2. Prompt 전체 확인
3. Context가 깨지는지 확인
4. Model Response Pattern 확인
5. Language Validation 확인
6. Retry 전략 확인
7. 후처리 전략 검토
8. 필요 시 Model 교체 비교
```

---

# 40. Generation을 새로 작성할 경우

현재 Generation 구조를 완전히 버리기 전에
기존 API Contract를 반드시 유지합니다.

유지해야 할 입력:

```text
query
announcement
retrieval results
```

유지해야 할 출력:

```text
GeneratedAnswer
sources
answer
```

Backend 최종 계약:

```text
answer
grounded
evidence
```

---

# 41. 새 Generation 구현 시 건드리지 않아도 되는 영역

가능하면 유지:

```text
rag/service.py
backend/app/services/chat_service.py
backend/app/api/routes/chat.py
backend/app/schemas/chat.py
frontend/user/
```

즉 Generation 내부만 교체할 수 있는 구조를 목표로 합니다.

---

# 42. Generation 해결 후 우선순위 2

```text
전체 기능 Smoke Test
```

확인:

```text
공고 목록
공고 상세
Chat
Evidence
Admin
Pipeline
Persistence
Activation
```

---

# 43. 우선순위 3

Crawler 구현 여부 결정.

현재 실제 자동 수집 기능이 없으므로
최종 프로젝트 요구사항에서 Crawler가 필수라면 구현해야 합니다.

현재는:

```text
crawler/__init__.py
```

만 존재합니다.

---

# 44. 우선순위 4

Admin 기능 실제 동작 검증.

확인:

```text
Login
Auth
Announcement
Document
Error
Pipeline Control
Logout
```

---

# 45. 우선순위 5

프로젝트 최종 정리.

검토:

```text
.env.example
requirements.txt
README.md
docs/
Legacy Reference
Temporary Files
outputs 정책
node_modules 정책
Model Path 정책
```

---

# 46. 현재 삭제하지 말아야 할 파일

```text
alembic.ini
run_pipeline.py
config/paths.py

pipeline/chunking/tokenizer.py
pipeline/embedding/model_loader.py

rag/db_pipeline.py
rag/service.py
rag/models.py
rag/retrieval/query_embedding.py

backend/app/services/pipeline_persistence.py
```

각 파일은 현재 Runtime 또는 Pipeline에서 중요한 역할을 합니다.

---

# 47. outputs 디렉터리

```text
outputs/
```

는 Source Code가 아니지만 현재:

```text
Pipeline Debug
Stage 비교
Persistence Input
```

에 필요합니다.

최종 배포/Repository 정책을 정하기 전까지 무조건 삭제하지 않습니다.

---

# 48. node_modules

```text
frontend/user/node_modules/
```

는 Source Code가 아닙니다.

npm으로 재생성할 수 있습니다.

```bash
npm install
```

최종 Repository 정책에서는 일반적으로 제외 대상입니다.

---

# 49. Model 파일

Qwen GGUF Model은 Project Root 외부:

```text
/home/ubuntu/ddokbot/models/
```

계열에 위치합니다.

대형 Model Binary를 프로젝트 Source Tree에 넣지 않습니다.

---

# 50. Environment Secret

공유하지 말아야 하는 것:

```text
.env 실제 Secret
PEM Private Key
DB Password
ADMIN_PASSWORD
ADMIN_JWT_SECRET
```

인수인계 시:

```text
.env.example
```

을 제공합니다.

---

# 51. 새 ChatGPT 세션에 프로젝트를 넘기는 방법

최소 먼저 전달:

```text
README.md
docs/HANDOVER.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
```

그리고 질문:

```text
이 프로젝트의 현재 구조와 미완료 상태를 먼저 이해해.
코드 수정은 아직 하지 마.
```

를 요청합니다.

---

# 52. Generation 문제를 새 AI에게 넘길 경우

추가 전달:

```text
docs/RAG.md
docs/TROUBLESHOOTING.md

rag/service.py
rag/db_pipeline.py
rag/models.py
rag/retrieval/
rag/generation/

backend/app/services/chat_service.py
backend/app/api/routes/chat.py
backend/app/schemas/chat.py
```

그리고 최근 Chat Response와 Traceback도 전달합니다.

---

# 53. AI에게 반드시 알려야 하는 현재 상태

```text
Retrieval은 일정 질문에서 관련 Evidence를 정상 검색한다.

현재 핵심 문제는 Generation이다.

Qwen 모델이 중국어를 섞어 출력하는 사례가 있다.

Validation을 강제하면 GenerationError가 발생했다.

현재 API는 Generation 실패 시 fallback Answer를 반환할 수 있다.

Frontend와 Backend 연결 자체는 확인되었다.
```

이 정보를 전달하면 AI가 불필요하게 Parser/DB/Frontend부터 다시 수정하는 일을 줄일 수 있습니다.

---

# 54. 하지 말아야 할 것

인수받은 직후 다음 작업을 하지 않습니다.

```text
RAG 전체를 무조건 새로 작성

Parser 전체 교체

DB Schema 재설계

Frontend API Contract 변경

파일 사용 여부 확인 없이 삭제

Generation 문제 때문에 Embedding 재생성

과거 Legacy README 기준으로 코드 되돌리기
```

먼저 현재 Runtime을 검증합니다.

---

# 55. 현재 Source of Truth

전체 구조:

```text
docs/ARCHITECTURE.md
```

파일 위치:

```text
docs/PROJECT_STRUCTURE.md
```

Pipeline:

```text
run_pipeline.py
docs/PIPELINE.md
```

Runtime RAG:

```text
rag/db_pipeline.py
docs/RAG.md
```

Backend:

```text
backend/app/
docs/BACKEND.md
```

Database:

```text
backend/app/models/
docs/DATABASE.md
```

Frontend:

```text
frontend/
docs/FRONTEND.md
```

Environment:

```text
.env.example
docs/ENVIRONMENT.md
```

문제 해결:

```text
docs/TROUBLESHOOTING.md
```

---

# 56. 인수인계 후 첫날 권장 작업

```text
1. 문서 읽기
2. Project Tree 확인
3. Python Compile
4. Frontend Build
5. DB Health
6. Backend Health
7. Announcement API
8. Chat API
9. Evidence 확인
10. Generation 문제 재현
```

코드 변경은 그 다음에 시작합니다.

---

# 57. Chat Generation 문제 재현용 기준 질문

현재 대표 테스트 질문:

```text
신청 일정은 언제인가?
```

기대 근거:

```text
2026년 7월 23일(목) 오전 10시부터 별도 공지시까지

운영시간:
10:00~16:00

12:00~13:00 및
주말·공휴일 미운영
```

이 질문을 기준으로 Generation 안정성을 반복 테스트할 수 있습니다.

---

# 58. 기대 최종 Answer 예

```text
신청 일정은 2026년 7월 23일(목) 오전 10시부터 별도 공지시까지입니다. 운영시간은 10:00~16:00이며, 12:00~13:00과 주말·공휴일에는 운영하지 않습니다.
```

이 Answer는 Retrieval된 공고문 내용만 사용합니다.

---

# 59. Generation 완료 판단 기준

다음이 모두 만족되면 Generation 문제를 상당 부분 해결했다고 판단합니다.

```text
[ ] 중국어/일본어 혼입 없음
[ ] 동일 질문 반복 시 안정적
[ ] 근거에 없는 정보 생성 없음
[ ] 숫자/날짜 변경 없음
[ ] Evidence 내용과 Answer 일치
[ ] Fallback 발생률 낮음
[ ] API 500 없음
[ ] Frontend 정상 표시
```

---

# 60. 최종 프로젝트 완료 조건

현재 프로젝트를 최종 완료로 판단하려면 최소:

```text
[ ] Pipeline 정상
[ ] Persistence 정상
[ ] Active Dataset 정상
[ ] Retrieval 정상
[ ] Generation 안정화
[ ] Backend API 정상
[ ] User Frontend 정상
[ ] Admin Frontend 검증
[ ] 환경 문서 정리
[ ] 전체 문서 최신화
[ ] 최종 Smoke Test
```

가 필요합니다.

---

# 61. 핵심 인수인계 요약

현재 가장 중요한 정보만 압축하면:

```text
1. Pipeline은 작동한다.

2. BGE-M3 + pgvector Retrieval도 작동한다.

3. FastAPI와 User Frontend 연결도 확인했다.

4. 관련 Evidence도 정상적으로 검색된다.

5. 현재 가장 큰 문제는 Qwen Generation 안정성이다.

6. 중국어 출력 때문에 Validation 오류가 발생한 적이 있다.

7. 현재는 API 전체가 죽지 않도록 fallback 구조가 있다.

8. 다음 작업은 Generation 계층부터 시작해야 한다.

9. Retrieval이 정상인 질문에서는 Parser/DB/Frontend를 먼저 수정하지 않는다.

10. 구조 변경 전 README와 docs 문서를 먼저 읽는다.
```

이 내용을 현재 프로젝트 인수인계의 기준으로 사용합니다.
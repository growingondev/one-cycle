# DDOKBOT Development Guide

> 이 문서는 DDOKBOT 프로젝트에서 실제 개발 작업을 수행할 때의 표준 절차를 설명합니다.
>
> 목적은 다음과 같습니다.
>
> - 개발 환경을 어떤 순서로 실행하는지
> - 수정하려는 기능에 따라 어느 파일을 봐야 하는지
> - Pipeline 재실행이 필요한지 판단하는 방법
> - DB 반영과 Active 전환 절차
> - Backend / Frontend 재실행 방법
> - curl, Build, Runtime 검증 순서
> - 문제 발생 시 수정 범위를 최소화하는 방법
>
> 프로젝트 구조 자체는 다음 문서를 먼저 참고합니다.
>
> ```text
> README.md
> docs/ARCHITECTURE.md
> docs/PROJECT_STRUCTURE.md
> ```

---

# 1. 개발 시작 전 기본 위치

프로젝트 Root:

```text
/home/ubuntu/ddokbot/one-cycle
```

기본 이동:

```bash
cd /home/ubuntu/ddokbot/one-cycle
```

Python:

```text
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python
```

---

# 2. 개발 시작 전 확인 순서

작업 시작 전에 최소 다음을 확인합니다.

```text
1. 프로젝트 Root
2. .env
3. PostgreSQL
4. llama.cpp
5. FastAPI
6. Frontend
```

모든 서비스를 무조건 다시 설치하거나 재구성하지 않습니다.

이미 실행 중이면 상태만 확인합니다.

---

# 3. 현재 작업 대상 먼저 분류

코드를 수정하기 전에 문제가 어느 영역인지 분류합니다.

```text
Parser
Normalizer
Structure
Chunking
Embedding
Persistence
Database
Retrieval
Generation
Backend
Frontend
Admin
```

가장 중요한 원칙:

> 문제가 발생한 계층을 먼저 찾고 해당 계층부터 수정한다.

---

# 4. 문제 분류 예

## HWP/HWPX 내용 자체가 잘못 읽힘

확인:

```text
pipeline/parser/
```

---

## Parser 결과는 맞지만 문자/표현이 이상함

확인:

```text
pipeline/normalizer/
```

---

## 문서 의미 구조가 이상함

확인:

```text
pipeline/structure/
```

---

## 검색 단위가 이상함

확인:

```text
pipeline/chunking/
```

---

## Embedding이 생성되지 않음

확인:

```text
pipeline/embedding/
```

---

## Pipeline Output은 정상인데 DB 데이터가 이상함

확인:

```text
backend/app/services/pipeline_persistence.py
```

---

## 검색 Evidence가 잘못됨

확인:

```text
rag/db_pipeline.py
rag/retrieval/query_embedding.py
```

---

## Evidence는 정확하지만 Answer가 이상함

확인:

```text
rag/generation/
```

---

## curl은 정상인데 Browser만 이상함

확인:

```text
frontend/
```

---

# 5. 개발 환경 실행 권장 순서

개발 환경을 처음 시작하는 경우:

```text
PostgreSQL
    ↓
llama.cpp
    ↓
FastAPI
    ↓
User Frontend
    ↓
SSH Tunnel
    ↓
Browser
```

---

# 6. PostgreSQL 확인

Backend가 이미 실행 중이면:

```bash
curl -i \
http://127.0.0.1:8000/api/health/db
```

직접 확인:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from sqlalchemy import text
from backend.app.db.session import engine

with engine.connect() as conn:
    result = conn.execute(
        text("SELECT 1")
    ).scalar_one()

print("[OK] DB:", result)
PY
```

정상:

```text
[OK] DB: 1
```

---

# 7. llama.cpp 확인

Generation 기능을 사용할 경우 llama.cpp 서버가 실행 중이어야 합니다.

현재 Generation 설정 확인:

```bash
cd /home/ubuntu/ddokbot/one-cycle

sed -n '1,220p' \
rag/generation/config.py
```

LLM Client:

```bash
sed -n '1,240p' \
rag/generation/llm_client.py
```

기본적으로 Local llama.cpp Endpoint를 사용합니다.

개념:

```text
127.0.0.1:8080
```

실제 현재 값은 코드가 Source of Truth입니다.

---

# 8. Backend 실행

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

# 9. Backend 기본 확인

다른 Terminal:

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

# 10. User Frontend 실행

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run dev
```

일반 개발 Port:

```text
5173
```

---

# 11. 로컬 Browser 연결

AWS 서버에서 개발 중이라면 로컬 PC에서 SSH Port Forwarding을 사용할 수 있습니다.

```bash
ssh -i <PEM_FILE_PATH> \
-L 5173:127.0.0.1:5173 \
ubuntu@<AWS_PUBLIC_IP>
```

Browser:

```text
http://127.0.0.1:5173
```

---

# 12. Backend도 로컬에서 직접 보고 싶을 경우

```bash
ssh -i <PEM_FILE_PATH> \
-L 5173:127.0.0.1:5173 \
-L 8000:127.0.0.1:8000 \
ubuntu@<AWS_PUBLIC_IP>
```

로컬:

```text
Frontend
http://127.0.0.1:5173

Backend
http://127.0.0.1:8000
```

---

# 13. 코드 수정 전 Reference 검색

파일을 수정하거나 삭제하기 전에 반드시 참조 관계를 확인합니다.

예:

```bash
grep -RHn \
'검색할함수또는파일명' \
backend pipeline rag config run_pipeline.py \
--include='*.py' \
--exclude-dir='__pycache__'
```

Frontend:

```bash
grep -RHn \
'검색할이름' \
frontend/user/src \
--include='*.ts' \
--include='*.tsx'
```

---

# 14. 파일 삭제 전 확인

다음은 단순 Import grep만으로 놓칠 수 있습니다.

```text
Dynamic Import
Environment Variable Function Path
subprocess 실행
Path 객체를 통한 Runner 실행
Frontend 문자열 참조
```

특히:

```text
RAG_ANSWER_FUNCTION
pipeline_gateway.py
run_pipeline.py
```

를 반드시 확인합니다.

---

# 15. Python 코드 수정 후 기본 검증

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

# 16. 중요한 Module Import Test

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from backend.app.main import app
from rag.service import answer_question
from rag.db_pipeline import DBRAGPipeline

print("[OK] imports")
PY
```

---

# 17. Frontend 수정 후 Build

User Frontend 수정 후:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run build
```

Build가 성공해야 다음 단계로 진행합니다.

---

# 18. Frontend Build에서 발견할 수 있는 문제

```text
TypeScript 변수명 오타
잘못된 Import
존재하지 않는 Component
문법 오류
API 변수명 오타
```

실제 프로젝트 정리 과정에서도:

```text
API_BASE_UR
```

오타가 Build 전 코드 점검 과정에서 발견되었습니다.

정상:

```text
API_BASE_URL
```

---

# 19. 어떤 수정에 Pipeline 재실행이 필요한가

모든 코드 수정 후 Pipeline을 다시 실행하는 것은 아닙니다.

다음 영역을 수정하면 Pipeline 재실행 여부를 검토합니다.

```text
Parser
Normalizer
Structure
Chunking
Embedding
```

---

# 20. Parser 수정

수정:

```text
pipeline/parser/
```

필요:

```text
parse
normalize
structure
chunk
embed
persist
activate
```

원칙적으로 Parser 이후 모든 결과에 영향을 줄 수 있습니다.

---

# 21. Normalizer 수정

필요:

```text
normalize
structure
chunk
embed
persist
activate
```

Parser 결과가 동일하다면 Parse부터 다시 실행하지 않아도 됩니다.

---

# 22. Structure 수정

필요:

```text
structure
chunk
embed
persist
activate
```

---

# 23. Chunking 수정

필요:

```text
chunk
embed
persist
activate
```

---

# 24. Embedding 수정

필요:

```text
embed
persist
activate
```

Embedding Model이나 Dimension이 변경되면 DB Schema 영향까지 확인합니다.

---

# 25. Generation 수정

수정:

```text
rag/generation/
```

일반적으로 필요 없음:

```text
Parser 재실행
Chunking 재실행
Embedding 재실행
DB Persistence
```

Generation만 다시 테스트하면 됩니다.

---

# 26. Retrieval SQL 수정

수정:

```text
rag/db_pipeline.py
```

DB 데이터 자체가 정상이라면 Pipeline을 다시 돌릴 필요가 없습니다.

직접 Retrieval 또는 Chat을 테스트합니다.

---

# 27. Frontend 수정

일반적으로:

```text
Pipeline 재실행 X
DB Persistence X
Embedding X
```

필요:

```text
npm run build
Frontend dev server
Browser 확인
```

---

# 28. Backend Route/Schema 수정

필요:

```text
Python Compile
Backend Restart
curl
Frontend 확인
```

DB Schema를 바꾸지 않았다면 Migration은 필요하지 않습니다.

---

# 29. DB Model 수정

수정:

```text
backend/app/models/
```

확인:

```text
migrations/
```

필요할 수 있는 절차:

```text
Model 변경
↓
Migration 작성
↓
alembic upgrade
↓
Backend Test
```

---

# 30. Pipeline Stage 실행

전체 Pipeline Runner:

```text
run_pipeline.py
```

Stage별 실행 예:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage parse
```

Normalize:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage normalize
```

Structure:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage structure
```

Chunk:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage chunk
```

Embedding:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
run_pipeline.py --stage embed
```

실제 지원 Stage 이름은 `run_pipeline.py --help`와 코드가 최종 기준입니다.

---

# 31. Pipeline Output 확인

```bash
find outputs \
-type f \
| sort
```

특정 Announcement:

```bash
find outputs/announcement_001 \
-type f \
| sort
```

---

# 32. Pipeline Debug 원칙

항상 처음 잘못된 Stage를 찾습니다.

```text
Original
 ↓
Parsed
 ↓
Normalized
 ↓
Structured
 ↓
Chunks
 ↓
Embeddings
```

예:

```text
Parsed 정상
Normalized 정상
Structured 정상
Chunks 오류
```

이면:

```text
Chunking
```

만 먼저 수정합니다.

Parser를 다시 작성하지 않습니다.

---

# 33. Persistence 전 Dry Run

Pipeline 결과가 정상이라면 DB에 쓰기 전 검증합니다.

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m backend.app.services.pipeline_persistence \
--announcement-key announcement_001
```

정상:

```text
DRY RUN: PASS
DB WRITE: NO
```

---

# 34. DB Write

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m backend.app.services.pipeline_persistence \
--announcement-key announcement_001 \
--write
```

정상 확인:

```text
DB WRITE: PASS
```

---

# 35. Write 후 즉시 서비스된다고 가정하지 않기

DB Write와 Activation은 별개일 수 있습니다.

확인해야 하는 상태:

```text
ProcessingRun.is_active
ChunkSet.is_active
```

새 데이터가 DB에 있어도 Active가 아니면 Runtime RAG에서 검색되지 않을 수 있습니다.

---

# 36. ProcessingRun Activation

예:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from backend.app.services.pipeline_persistence import (
    activate_processing_run,
)

result = activate_processing_run(5)

print(result)
PY
```

실제 Processing Run ID를 사용합니다.

---

# 37. Active 상태 확인

개념:

```text
Document
 ├── ProcessingRun 4 active=False
 └── ProcessingRun 5 active=True
```

ChunkSet도 해당 Active Run과 일치해야 합니다.

---

# 38. Retrieval 단독 테스트

Generation 문제와 Retrieval 문제를 분리하기 위해 Retrieval만 테스트할 수 있습니다.

예:

```bash
cd /home/ubuntu/ddokbot/one-cycle

set -a
source .env
set +a

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from rag.db_pipeline import DBRAGPipeline

pipeline = DBRAGPipeline.from_database()

results = pipeline.retrieve(
    announcement_id=1,
    query="신청 일정은 언제인가?",
)

for index, result in enumerate(results, start=1):
    print()
    print(index)
    print("chunk:", result.chunk_id)
    print("score:", result.score)
    print("title:", result.item.title)
    print("content:", result.item.content[:500])
PY
```

※ `RetrievalResult`의 실제 Property 이름은 현재 `rag/models.py`를 최종 기준으로 사용합니다.

---

# 39. Retrieval Test의 목적

결과에 다음과 같은 일정 근거가 검색된다면:

```text
‘26.07.23.(목) 오전 10시 ~ 별도 공지시까지
```

Retrieval은 정상입니다.

이 상태에서 Answer만 이상하면 Generation을 확인합니다.

---

# 40. Generation 포함 RAG 테스트

```bash
cd /home/ubuntu/ddokbot/one-cycle

set -a
source .env
set +a

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from rag.db_pipeline import DBRAGPipeline

pipeline = DBRAGPipeline.from_database()

result = pipeline.ask(
    announcement_id=1,
    query="신청 일정은 언제인가?",
)

print("ANSWER:")
print(result.answer)

print()
print("SOURCES:")
print(len(result.sources))
PY
```

---

# 41. RAG 테스트 판단

## Retrieval 결과부터 틀림

수정:

```text
query_embedding
DB Retrieval
Chunk/Embedding 데이터
```

---

## Retrieval 정상 + Generation 실패

수정:

```text
rag/generation/
```

---

## Python RAG 테스트 정상 + API 실패

확인:

```text
rag/service.py
chat_service.py
chat.py
```

---

## API 정상 + Browser 실패

확인:

```text
frontend/
Vite Proxy
```

---

# 42. Chat API Test

```bash
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

# 43. Chat Response에서 볼 것

```text
HTTP Status
answer
grounded
evidence count
evidence content
score
```

---

# 44. HTTP 200 + fallback Answer

예:

```text
grounded=true
evidence 존재
answer=fallback
```

이 경우 Frontend나 DB를 다시 뜯지 않습니다.

우선:

```text
rag/generation/
```

을 확인합니다.

---

# 45. Backend 수정 후 재시작

Uvicorn을 `--reload` 없이 실행했다면 Python 코드 수정 후 Process를 다시 시작해야 합니다.

현재 실행 Process를 종료하고:

```text
Ctrl + C
```

다시:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m uvicorn backend.app.main:app \
--host 127.0.0.1 \
--port 8000
```

을 실행합니다.

---

# 46. Environment 변경 후 재시작

`.env`를 변경했다면 기존 Process가 이미 값을 읽고 있을 수 있습니다.

따라서:

```text
Backend Restart
```

가 필요할 수 있습니다.

llama.cpp 관련 설정을 변경했다면 LLM Server도 확인합니다.

---

# 47. Frontend 수정 후 Dev Server

Vite는 개발 중 변경 사항을 자동 반영할 수 있습니다.

하지만 다음은 반드시 별도 실행합니다.

```bash
npm run build
```

개발 화면이 정상이라고 Build도 반드시 성공하는 것은 아닙니다.

---

# 48. 개발 작업 완료 전 최소 Smoke Test

다음 순서로 확인합니다.

```text
[ ] Python compile
[ ] 중요 Module import
[ ] Backend health
[ ] DB health
[ ] Announcement list
[ ] Announcement detail
[ ] Retrieval
[ ] Chat API
[ ] Frontend build
[ ] Browser list
[ ] Browser detail
[ ] Browser chat
```

---

# 49. Backend API Smoke Test

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

Detail:

```bash
curl -i \
http://127.0.0.1:8000/api/announcements/1
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

# 50. Frontend Smoke Test

Browser에서:

```text
Intro
 ↓
공고 목록
 ↓
공고 선택
 ↓
상세 화면
 ↓
질문 입력
 ↓
AI 답변
 ↓
Evidence
```

까지 확인합니다.

---

# 51. 관리자 화면 수정 후 확인

관리자 기능을 수정했다면 별도로:

```text
Login
Auth Check
Announcement
Document
Error
Logout
```

흐름을 확인합니다.

Admin Frontend:

```text
frontend/admin/
```

Backend:

```text
backend/app/api/routes/admin.py
backend/app/api/routes/admin_auth.py
```

---

# 52. 코드 수정 범위를 최소화하기

예를 들어:

```text
LLM이 중국어를 섞어서 생성
```

라는 문제라면 처음부터:

```text
Parser
Normalizer
Chunking
DB
Frontend
```

까지 바꾸지 않습니다.

확인 순서:

```text
Evidence 정상?
   ↓ yes
Generation Raw Response
   ↓
Prompt
   ↓
LLM 설정
   ↓
Response Validation
```

입니다.

---

# 53. 다른 예

문제:

```text
신청 일정 질문에 계약서류 Chunk가 1위 검색됨
```

확인:

```text
Query Embedding
Chunk Search Text
pgvector Similarity
Top-K
```

필요하면 Chunking/Embedding까지 역추적합니다.

하지만 Answer Prompt부터 수정해서 검색 문제를 숨기지 않습니다.

---

# 54. Runtime 데이터와 Source Code 구분

다음은 Source Code가 아닙니다.

```text
outputs/
frontend/user/node_modules/
frontend/user/dist/
__pycache__/
```

이러한 Artifact와 Source Code 수정 문제를 구분합니다.

---

# 55. __pycache__ 정리

필요하면:

```bash
cd /home/ubuntu/ddokbot/one-cycle

find . \
-type d \
-name '__pycache__' \
-prune \
-exec rm -rf {} +
```

삭제해도 Python 실행 시 다시 생성됩니다.

---

# 56. Frontend node_modules 재생성

문제가 있을 경우:

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

rm -rf node_modules

npm install
```

단 의존성 문제가 아닌데 무조건 `node_modules`부터 지우지 않습니다.

---

# 57. outputs 삭제 주의

`outputs/`는 Source Code가 아니지만 Pipeline Debug와 Persistence 입력으로 사용할 수 있습니다.

따라서 작업 중 무조건 삭제하지 않습니다.

삭제 전:

```text
Pipeline 재생성 가능 여부
Persistence 완료 여부
Debug 필요 여부
```

를 확인합니다.

---

# 58. DB 데이터 삭제 주의

ProcessingRun/Chunk/Embedding 데이터를 수동 SQL로 바로 삭제하기보다 기존 Service와 Active 구조를 먼저 이해합니다.

특히:

```text
ProcessingRun
ChunkSet
SystemState
```

의 관계를 깨뜨리지 않도록 합니다.

---

# 59. 개발 중 SQL 직접 수정 원칙

조회/검증 SQL은 자유롭게 사용할 수 있습니다.

예:

```sql
SELECT ...
```

하지만 상태 변경:

```sql
UPDATE
DELETE
```

는 가능한 기존 Service/Activation Logic을 사용합니다.

---

# 60. 개발 완료 후 문서 동기화

다음 구조가 바뀌었다면 문서도 수정합니다.

```text
파일 경로
API
환경변수
Pipeline Stage
DB Schema
RAG 흐름
실행 Port
```

관련 문서:

```text
README.md
docs/
```

---

# 61. 문서와 코드가 다를 경우

항상:

```text
실제 실행 코드
```

가 최종 Source of Truth입니다.

문서가 오래되었다면 코드를 문서에 맞추는 것이 아니라,
현재 의도된 Runtime 구조를 확인한 뒤 문서를 갱신합니다.

---

# 62. 작업 종료 전 Legacy Reference 검색

구조를 바꿨다면 이전 이름이 남아 있는지 검색합니다.

예:

```bash
grep -RHnE \
'RerankResult|rag\.reranker|HybridSearcher|hybrid_search|bm25_search|18000|API_BASE_UR' \
backend pipeline rag frontend config docs run_pipeline.py \
--include='*.py' \
--include='*.md' \
--include='*.ts' \
--include='*.tsx' \
--include='*.js' \
--exclude-dir='node_modules' \
--exclude-dir='__pycache__' \
|| true
```

출력이 없거나 의도된 문서 설명만 있어야 합니다.

---

# 63. 프로젝트 구조 확인

```bash
cd /home/ubuntu/ddokbot/one-cycle

find . \
-maxdepth 3 \
-not -path '*/node_modules/*' \
-not -path '*/__pycache__/*' \
-not -path './outputs/*' \
| sort
```

새로운 임시 파일이나 중복 폴더가 생기지 않았는지 확인합니다.

---

# 64. Markdown 문서 확인

```bash
find . \
-type f \
-name '*.md' \
-not -path '*/node_modules/*' \
| sort
```

공식 문서는 `README.md`와 `docs/` 중심으로 유지합니다.

---

# 65. 하루 개발 작업 표준 순서

권장:

```text
1. 작업 목표 정의
2. 문제 계층 판단
3. 관련 문서 확인
4. Source Code 확인
5. Reference 검색
6. 최소 범위 수정
7. Compile/Build
8. Unit 성격의 직접 실행
9. API Test
10. Browser Test
11. Legacy Reference 검색
12. 문서 갱신
```

---

# 66. Pipeline 작업 표준 순서

```text
1. 변경 Stage 결정
2. 해당 Stage 입력 확인
3. 코드 수정
4. 해당 Stage 실행
5. Output 확인
6. 이후 Stage 실행
7. Embedding 검증
8. Persistence Dry Run
9. DB Write
10. Activation
11. Retrieval Test
12. Chat Test
```

---

# 67. RAG 작업 표준 순서

```text
1. 질문 고정
2. Retrieval 결과 확인
3. Evidence 확인
4. Context 확인
5. Prompt 확인
6. Raw LLM Response 확인
7. Validation 확인
8. Chat API 확인
9. Frontend 확인
```

---

# 68. Frontend 작업 표준 순서

```text
1. API curl 정상 여부 확인
2. Component 수정
3. npm run build
4. npm run dev
5. Browser Console
6. Browser Network
7. UI 확인
```

---

# 69. Backend 작업 표준 순서

```text
1. Route/Schema/Service 범위 결정
2. 코드 수정
3. compileall
4. Import Test
5. Backend Restart
6. Health
7. 해당 API curl
8. Frontend 확인
```

---

# 70. Database 작업 표준 순서

```text
1. 현재 Model 확인
2. 현재 Migration 확인
3. 변경 범위 결정
4. ORM 수정
5. Migration 작성
6. Migration Review
7. Upgrade
8. DB Query 검증
9. Backend Test
10. RAG Test
```

---

# 71. AI에게 개발 작업을 맡길 때

최소 먼저 전달:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/DEVELOPMENT.md
```

그 다음 작업에 맞는 문서를 추가합니다.

Pipeline:

```text
docs/PIPELINE.md
```

RAG:

```text
docs/RAG.md
```

Backend:

```text
docs/BACKEND.md
docs/API.md
```

Frontend:

```text
docs/FRONTEND.md
```

DB:

```text
docs/DATABASE.md
```

Environment:

```text
docs/ENVIRONMENT.md
```

---

# 72. AI에게 코드를 맡길 때 중요한 요청 방식

나쁜 요청:

```text
프로젝트가 이상해. 다 고쳐줘.
```

권장 요청:

```text
POST /api/chat은 HTTP 200이고 evidence도 정확하다.
하지만 answer가 fallback이다.

Retrieval은 정상으로 보고 Generation 계층만 우선 분석해라.

API 계약은 변경하지 말고
rag/generation/ 내부에서 최소 수정으로 해결해라.
```

문제 범위와 유지해야 할 Contract를 명확히 전달합니다.

---

# 73. 작업 완료 판단

작업 완료는:

```text
코드가 저장됨
```

이 아닙니다.

최소:

```text
실행
검증
API
UI
```

까지 정상이어야 합니다.

---

# 74. 최종 Check List

```text
[ ] 관련 Source Code 정리 완료
[ ] 중복/Legacy 참조 없음
[ ] Python Compile 성공
[ ] 주요 Import 성공
[ ] DB Health 정상
[ ] Backend Health 정상
[ ] Announcement API 정상
[ ] Detail API 정상
[ ] Retrieval 정상
[ ] Chat API 정상
[ ] Frontend Build 성공
[ ] Browser 연결 성공
[ ] 관련 문서 갱신
```

---

# 75. 핵심 원칙 요약

DDOKBOT 개발에서 가장 중요한 원칙은 다음입니다.

```text
문제를 계층별로 분리한다.

최소 범위만 수정한다.

Stage 사이 Contract를 유지한다.

Pipeline과 Runtime을 구분한다.

DB Write와 Activation을 구분한다.

Retrieval과 Generation을 구분한다.

API와 Frontend를 구분한다.

수정 후 반드시 실제 실행으로 검증한다.
```

이 원칙을 지키면 하나의 오류를 해결하기 위해 프로젝트 전체를 불필요하게 수정하는 일을 줄일 수 있습니다.
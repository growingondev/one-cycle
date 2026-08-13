# DDOKBOT Troubleshooting Guide

> 이 문서는 DDOKBOT 개발 및 실행 과정에서 자주 발생하거나 실제로 발생했던 문제를 빠르게 진단하기 위한 문서입니다.
>
> 형식:
>
> ```text
> 증상
> → 가능한 원인
> → 확인 방법
> → 수정 위치
> ```
>
> 문제가 발생했을 때 프로젝트 전체를 수정하지 말고,
> 먼저 문제가 어느 계층에서 발생했는지 분리하는 것을 원칙으로 합니다.

---

# 1. 가장 먼저 문제 계층을 구분하기

DDOKBOT 문제는 대체로 다음 영역 중 하나입니다.

```text
Environment
Database
Pipeline
Persistence
Retrieval
Generation
Backend API
Frontend
SSH / Network
```

가장 먼저 아래 질문에 답합니다.

```text
1. Backend가 살아 있는가?
2. DB가 연결되는가?
3. API가 curl에서 정상인가?
4. Evidence가 정상인가?
5. Answer만 이상한가?
6. Browser에서만 실패하는가?
```

---

# 2. Backend가 살아 있는지 확인

확인:

```bash
curl -i \
http://127.0.0.1:8000/api/health
```

정상:

```text
HTTP/1.1 200 OK
```

실패한다면:

```text
FastAPI 미실행
Port 오류
Process 종료
잘못된 Host
```

가능성이 있습니다.

확인:

```bash
ps -ef | grep uvicorn
```

---

# 3. DB 연결 확인

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

# 4. DB Authentication Failed

증상:

```text
password authentication failed
```

또는:

```text
OperationalError
```

가능한 원인:

```text
DB USER 오류
DB PASSWORD 오류
HOST 오류
PORT 오류
DATABASE NAME 오류
```

확인:

```text
.env
backend/app/core/config.py
backend/app/db/session.py
infra/docker-compose.yml
```

이 문제는 RAG나 Frontend 문제가 아닙니다.

---

# 5. PostgreSQL은 연결되지만 RAG 검색 결과가 없음

증상:

```text
DB pgvector 검색 결과가 없습니다.
```

확인 순서:

```text
1. announcement_id가 맞는가?
2. Active Collection인가?
3. Active ProcessingRun이 있는가?
4. Active ChunkSet이 있는가?
5. Chunk status가 completed인가?
6. Embedding status가 completed인가?
7. model_name이 일치하는가?
8. dimension이 1024인가?
9. normalized가 TRUE인가?
10. embedding이 NULL이 아닌가?
```

관련 코드:

```text
rag/db_pipeline.py
```

---

# 6. Active ProcessingRun 확인

예:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
from sqlalchemy import text
from backend.app.db.session import SessionLocal

sql = text("""
SELECT
    pr.id AS processing_run_id,
    pr.is_active AS processing_run_active,
    cs.id AS chunk_set_id,
    cs.is_active AS chunk_set_active,
    COUNT(c.id) AS chunk_count
FROM processing_runs pr
JOIN chunk_sets cs
  ON cs.processing_run_id = pr.id
JOIN chunks c
  ON c.chunk_set_id = cs.id
WHERE pr.document_id = 1
  AND pr.is_active = TRUE
  AND cs.is_active = TRUE
GROUP BY
    pr.id,
    pr.is_active,
    cs.id,
    cs.is_active
""")

with SessionLocal() as db:
    rows = db.execute(sql).mappings().all()

for row in rows:
    print(dict(row))
PY
```

정상 예:

```text
processing_run_active=True
chunk_set_active=True
chunk_count > 0
```

---

# 7. Pipeline Write는 성공했는데 새 데이터가 검색되지 않음

증상:

```text
DB WRITE: PASS
```

인데 Runtime RAG는 이전 데이터만 검색함.

가능한 원인:

```text
새 ProcessingRun이 Active가 아님
새 ChunkSet이 Active가 아님
```

확인:

```text
ProcessingRun.is_active
ChunkSet.is_active
```

필요하면:

```text
activate_processing_run(...)
```

을 사용합니다.

---

# 8. Chunk Count와 Embedding Count가 다름

증상:

```text
chunks = 291
embeddings = 290
```

원인 후보:

```text
Embedding 생성 실패
특정 Chunk 누락
Persistence 누락
Validation 실패
```

확인:

```text
pipeline/embedding/
backend/app/services/pipeline_persistence.py
```

정상 기준:

```text
Chunk Count == Embedding Count
```

---

# 9. BGE-M3 Model Load 실패

증상:

```text
CUDA Error
Model Load Error
FlagEmbedding Error
```

확인:

```bash
nvidia-smi
```

Python:

```bash
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
import torch

print(torch.__version__)
print(torch.version.cuda)
print(torch.cuda.is_available())

if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0))
PY
```

관련 코드:

```text
pipeline/embedding/model_loader.py
```

---

# 10. Query Embedding Dimension 오류

증상:

```text
질문 임베딩 차원이 1024가 아닙니다.
```

원인:

```text
Embedding Model 변경
잘못된 Model Load
Document Embedding과 Query Embedding 불일치
```

확인:

```text
pipeline/embedding/model_loader.py
rag/retrieval/query_embedding.py
rag/db_pipeline.py
backend/app/models/embedding.py
```

---

# 11. Retrieval 결과는 나오지만 순위가 이상함

증상:

```text
질문:
신청 일정은 언제인가?

1위:
계약 서류

2위:
신청 일정
```

가능한 원인:

```text
Dense Embedding Similarity 특성
Search Text 구성
Chunk Content 구성
Top-K 부족
Chunking 품질
```

확인:

```text
rag/db_pipeline.py
rag/retrieval/query_embedding.py
pipeline/chunking/text_builder.py
pipeline/chunking/
```

먼저 Top-K 전체를 보고 실제 관련 Chunk가 포함되는지 확인합니다.

---

# 12. Retrieval만 직접 테스트

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
    print(result)
PY
```

목적:

```text
Generation을 제외하고 Retrieval 자체가 정상인지 확인
```

---

# 13. Evidence는 정상인데 Answer가 이상함

가장 중요한 진단 사례입니다.

증상:

```json
{
  "grounded": true,
  "evidence": [
    {
      "content": "신청 일정은 ..."
    }
  ],
  "answer": "이상한 답변"
}
```

판단:

```text
Retrieval은 성공 가능성이 높음
Generation 계층을 우선 확인
```

수정 위치:

```text
rag/generation/context_builder.py
rag/generation/prompt_builder.py
rag/generation/llm_client.py
rag/generation/generator.py
```

Parser나 DB부터 다시 수정하지 않습니다.

---

# 14. Qwen이 중국어를 섞어 출력함

실제 발생 예:

```text
12:00~13:00은 휴憩时间...
```

또는:

```text
这里是中文
```

가능한 원인:

```text
Model 자체 Generation 성향
Prompt 언어 제약 부족
Quantized Model 품질
Generation Decoding 특성
```

현재 적용된 대응:

```text
temperature = 0.0
top_p = 1.0
```

Prompt에도:

```text
반드시 한국어로만 작성
중국어/일본어 포함 금지
```

규칙을 추가했습니다.

---

# 15. 중국어 검증에서 GenerationError 발생

증상:

```text
GenerationError:
LLM 답변에 허용하지 않는 중국어/일본어 문자가 포함되었습니다.
```

의미:

```text
LLM 호출 자체는 성공했지만
생성 결과 Validation에서 거부됨
```

확인:

```text
rag/generation/generator.py
```

특히:

```text
validate_korean_answer()
```

관련 로직을 확인합니다.

---

# 16. Validation이 계속 실패해서 HTTP 500이 발생함

과거 실제 흐름:

```text
LLM Chinese Output
 ↓
validate_korean_answer()
 ↓
GenerationError
 ↓
RAGServiceError
 ↓
500 Internal Server Error
```

이 경우 문제 핵심은:

```text
Frontend X
DB X
Retrieval X
Generation Validation
```

입니다.

---

# 17. Generation Retry도 같은 Validation에서 실패함

증상:

```text
첫 생성 실패
→ Retry
→ Retry도 중국어 포함
→ GenerationError
```

판단:

단순 Retry만으로 해결되지 않는 Model Output 문제입니다.

대응 선택지:

```text
Prompt 강화
Generation Parameter 변경
출력 후처리
Fallback
Model 교체
```

현재 MVP에서는 API 전체가 500이 되지 않도록 Fallback 처리를 사용할 수 있습니다.

---

# 18. HTTP 200인데 fallback 답변이 나옴

예:

```text
공고문 근거는 확인되었지만 현재 답변 생성 품질이 안정적이지 않아
정확한 문장으로 제공하지 못했습니다.
```

Response:

```text
grounded=true
evidence 존재
```

이 경우:

```text
API 연결 정상
DB 검색 정상 가능성 높음
Generation 실패
```

입니다.

이 상태를 Frontend 실패라고 판단하지 않습니다.

---

# 19. llama.cpp Connection Refused

증상:

```text
llama.cpp 서버에 연결할 수 없습니다.
```

확인:

```text
llama.cpp Process
Port
rag/generation/config.py
rag/generation/llm_client.py
```

기본 개발 구조:

```text
127.0.0.1:8080
```

Process 확인:

```bash
ps -ef | grep llama
```

---

# 20. llama.cpp Timeout

증상:

```text
llama.cpp 응답 시간이 초과되었습니다.
```

원인 후보:

```text
Model 응답 지연
GPU 문제
Server 과부하
max_tokens 과다
Context 과다
```

확인:

```text
rag/generation/config.py
```

주요 값:

```text
timeout_seconds
max_tokens
context_top_k
max_chars_per_context
```

---

# 21. PromptPayload TypeError

실제 발생 예:

```text
TypeError

PromptPayload.__init__() missing 4 required positional arguments:
'query',
'announcement_directory',
'document_format',
'sources'
```

원인:

```text
PromptPayload Model과 생성 코드 Contract 불일치
```

확인:

```text
rag/generation/models.py
rag/generation/prompt_builder.py
rag/generation/generator.py
```

특히 다른 Generation 구현을 일부만 복사했을 때 발생할 수 있습니다.

---

# 22. Generation 폴더를 통째로 교체할 때 발생할 수 있는 문제

서로 다른 Generation 구현은 다음 Contract가 다를 수 있습니다.

```text
PromptPayload
GeneratedAnswer
SourceContext
generate_answer()
generate_from_rerank_results()
generate()
```

따라서 파일 하나만 교체하면 Import는 되더라도 Runtime Contract가 깨질 수 있습니다.

교체 전 반드시 비교:

```text
models.py
generator.py
context_builder.py
prompt_builder.py
__init__.py
```

---

# 23. API 호출 후 JSON Parsing Error

증상:

```text
Expecting value: line 1 column 1 (char 0)
```

대부분 의미:

```text
Client는 JSON을 기대했지만
Server가 JSON이 아닌 응답을 반환
```

대표 원인:

```text
HTTP 500
text/plain Traceback
HTML Error Page
빈 Response
```

먼저 `response.json()` 하지 말고 Raw Response를 확인합니다.

---

# 24. curl -i로 Raw Response 확인

```bash
curl -i \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{"announcementId":1,"question":"신청 일정은 언제인가?"}'
```

확인:

```text
HTTP Status
Content-Type
Response Body
```

500이면 JSON Parser부터 수정하지 않습니다.

---

# 25. FastAPI 500 Internal Server Error

증상:

```text
HTTP/1.1 500 Internal Server Error
```

가장 중요한 정보:

```text
Uvicorn Terminal의 Traceback
```

Traceback에서 가장 처음 발생한 Project 내부 Exception을 찾습니다.

예:

```text
GenerationError
DBRAGPipelineError
RAGServiceError
SQLAlchemy Error
```

---

# 26. FastAPI 422

증상:

```text
422 Unprocessable Entity
```

가능한 원인:

```text
Request Field 이름 오류
Required Field 누락
Type 오류
Question 길이 오류
```

Chat Request 정상 예:

```json
{
  "announcementId": 1,
  "question": "질문"
}
```

잘못된 예:

```json
{
  "announcement_id": 1,
  "query": "질문"
}
```

Frontend Contract와 Backend Schema를 함께 확인합니다.

---

# 27. FastAPI 503

Chat API에서:

```text
503 Service Unavailable
```

가능한 원인:

```text
RAG_ANSWER_FUNCTION 미설정
Module Import 실패
Function 이름 오류
```

확인:

```bash
grep '^RAG_ANSWER_FUNCTION=' .env
```

정상 예:

```text
RAG_ANSWER_FUNCTION=rag.service:answer_question
```

---

# 28. RAG_ANSWER_FUNCTION Import 확인

```bash
cd /home/ubuntu/ddokbot/one-cycle

set -a
source .env
set +a

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python - <<'PY'
import os
import importlib

target = os.getenv("RAG_ANSWER_FUNCTION")
print("target:", target)

module_name, function_name = target.split(":", 1)

module = importlib.import_module(module_name)
function = getattr(module, function_name)

print("[OK]", function)
PY
```

---

# 29. Frontend 공고 목록이 안 나옴

먼저 Backend:

```bash
curl -i \
http://127.0.0.1:8000/api/announcements
```

정상이라면 Frontend 확인:

```text
frontend/user/src/config.ts
frontend/user/vite.config.ts
frontend/user/src/components/screens/ListScreen.tsx
```

---

# 30. API_BASE_UR 오타

실제 발견된 문제:

```text
API_BASE_UR
```

정상:

```text
API_BASE_URL
```

검색:

```bash
grep -RHn \
'API_BASE_UR' \
frontend/user/src \
--include='*.ts' \
--include='*.tsx'
```

주의:

`API_BASE_URL`도 `API_BASE_UR` 문자열을 포함하므로
검색 결과를 사람이 확인해야 합니다.

---

# 31. Frontend Build 확인

```bash
cd /home/ubuntu/ddokbot/one-cycle/frontend/user

npm run build
```

현재 정상 Build 기준:

```text
vite build
✓ built
```

Build 성공은 TypeScript/Import/기본문법이 정상이라는 중요한 신호입니다.

---

# 32. Browser는 열리는데 API가 실패함

가능한 원인:

```text
Vite Proxy
FastAPI 미실행
잘못된 Port
API Base 오류
```

확인:

```text
frontend/user/src/config.ts
frontend/user/vite.config.ts
```

현재 API Base:

```text
/api
```

입니다.

---

# 33. curl은 정상인데 Browser만 실패함

판단:

```text
Backend 문제 가능성 낮음
Frontend/Proxy/Browser Network 우선
```

확인:

```text
Browser Developer Tools
→ Network
→ Console
```

Network에서:

```text
Request URL
HTTP Status
Response
```

를 확인합니다.

---

# 34. Failed to fetch

가능성:

```text
Vite 서버 종료
FastAPI 종료
Proxy 오류
SSH Tunnel 종료
잘못된 Host
```

확인:

```bash
ps -ef | grep vite
ps -ef | grep uvicorn
```

---

# 35. SSH Identity File 오류

실제 발생 예:

```text
Warning: Identity file hancom-prod-team1-5th.pem not accessible
```

의미:

```text
로컬 PC에서 PEM 파일 경로를 찾지 못함
```

확인:

```bash
ls -l /실제/PEM/경로/hancom-prod-team1-5th.pem
```

SSH:

```bash
ssh -i /실제/PEM/경로/hancom-prod-team1-5th.pem \
-L 5173:127.0.0.1:5173 \
ubuntu@<AWS_PUBLIC_IP>
```

---

# 36. Permission denied (publickey)

증상:

```text
Permission denied (publickey)
```

가능한 원인:

```text
PEM 파일 없음
잘못된 PEM
잘못된 User
잘못된 AWS Host
PEM Permission
```

확인:

```bash
chmod 400 /path/to/key.pem
```

AWS Ubuntu 계열 기본 User는 현재 환경에서:

```text
ubuntu
```

를 사용합니다.

---

# 37. SSH는 연결됐는데 Frontend가 안 열림

확인:

AWS 서버:

```bash
ps -ef | grep vite
```

또는:

```bash
curl -I \
http://127.0.0.1:5173
```

정상이라면 SSH Tunnel 확인:

```text
-L 5173:127.0.0.1:5173
```

Browser:

```text
http://127.0.0.1:5173
```

---

# 38. Backend 8000 Port는 로컬 Forwarding이 꼭 필요한가

User Frontend의 Vite Proxy가 같은 AWS 서버 내부에서 FastAPI를 호출한다면:

```text
5173 Forwarding만으로도
Frontend + API가 함께 동작 가능
```

구조:

```text
Local Browser
  ↓
SSH 5173
  ↓
AWS Vite
  ↓
AWS FastAPI :8000
```

Backend를 로컬에서 직접 curl하고 싶을 때만:

```text
-L 8000:127.0.0.1:8000
```

을 추가합니다.

---

# 39. ModuleNotFoundError

증상:

```text
ModuleNotFoundError: No module named ...
```

확인:

```text
현재 Working Directory
PYTHONPATH
Python Interpreter
Virtualenv
```

권장:

```bash
cd /home/ubuntu/ddokbot/one-cycle

PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python ...
```

---

# 40. 잘못된 Python Virtualenv 사용

확인:

```bash
which python
python --version
```

명시 실행:

```text
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python
```

환경마다 Package가 다를 수 있으므로 시스템 Python과 섞지 않습니다.

---

# 41. `source .env` 했는데 값이 안 들어감

일반적인 Shell에서:

```bash
set -a
source .env
set +a
```

를 사용합니다.

이유:

일부 코드가:

```python
os.getenv(...)
```

를 직접 사용합니다.

Pydantic Settings와 Shell Environment를 혼동하지 않습니다.

---

# 42. `.env` 변경했는데 서버에서 반영 안 됨

기존 Process가 이미 환경변수를 읽었을 수 있습니다.

조치:

```text
FastAPI Restart
```

필요하면:

```text
llama.cpp Restart
Frontend Restart
```

도 해당 설정 영역에 따라 수행합니다.

---

# 43. HWP Parser 실패

확인:

```text
pipeline/parser/hwp_parser.py
pipeline/parser/common.py
pipeline/parser/libs/hwp/
JPype
Java Runtime
```

Parser 이후 Stage를 수정하지 않습니다.

---

# 44. HWPX Parser 실패

확인:

```text
pipeline/parser/hwpx_parser.py
pipeline/parser/common.py
pipeline/parser/libs/hwpx/
```

---

# 45. Normalizer가 잘못된 문자를 생성함

확인:

```text
pipeline/normalizer/document_normalizer.py
```

특히:

```text
special character
control character
PUA
unit normalization
```

관련 로직을 봅니다.

---

# 46. Structured 결과가 이상함

확인:

```text
pipeline/structure/run_structure.py
pipeline/structure/build_document_step1.py
pipeline/structure/build_domain_step2.py
pipeline/structure/build_table_step3.py
pipeline/structure/domain_rules.json
```

Normalized 결과가 정상인지 먼저 확인합니다.

---

# 47. Chunk 내용이 이상함

확인:

```text
pipeline/chunking/section_walker.py
pipeline/chunking/paragraph_chunker.py
pipeline/chunking/table_chunker.py
pipeline/chunking/text_builder.py
```

Structured 결과부터 확인합니다.

---

# 48. Table 검색이 이상함

공고문 일정/소득/주택형 등은 Table 의미가 중요합니다.

확인:

```text
pipeline/structure/build_table_step3.py
pipeline/chunking/table_chunker.py
pipeline/chunking/text_builder.py
```

행/열 관계가 깨졌는지 확인합니다.

---

# 49. Pipeline Stage 실행 결과가 이전 파일을 사용함

가능한 원인:

```text
outputs에 이전 결과 존재
Stage Skip Logic
새 파일이 생성되지 않음
```

확인:

```text
run_pipeline.py
outputs/
```

파일 수정 시간:

```bash
find outputs/announcement_001 \
-type f \
-printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' \
| sort
```

---

# 50. `outputs/`를 지워도 되는지

`outputs/`는 Source Code는 아닙니다.

하지만:

```text
Pipeline Debug
Persistence Input
Stage 비교
```

에 사용합니다.

무조건 삭제하지 않습니다.

삭제 전 재생성 가능한지 확인합니다.

---

# 51. `node_modules/`가 너무 큼

정상입니다.

```text
frontend/user/node_modules/
```

는 npm Dependency입니다.

Source Code가 아닙니다.

재생성 가능:

```bash
npm install
```

---

# 52. `__pycache__`가 계속 생성됨

정상입니다.

Python 실행 시 자동 생성됩니다.

삭제:

```bash
find . \
-type d \
-name '__pycache__' \
-prune \
-exec rm -rf {} +
```

삭제 후 다시 생길 수 있습니다.

---

# 53. `alembic.ini`가 Root에 있는 게 이상해 보임

정상입니다.

경로:

```text
/alembic.ini
```

역할:

```text
Alembic CLI 설정
```

DB Python Package 내부에 넣는 파일이 아닙니다.

연결:

```text
alembic.ini
 ↓
migrations/env.py
 ↓
ORM Models
```

---

# 54. Markdown 문서가 서로 다른 내용을 말함

공식 문서 Source:

```text
README.md
docs/
```

코드와 문서가 충돌하면:

```text
실제 실행 코드
```

가 우선입니다.

그 후 문서를 코드에 맞게 갱신합니다.

과거 README나 Legacy 문서를 그대로 참고하지 않습니다.

---

# 55. Legacy RAG 코드 흔적 발견

현재 Runtime 구조에서 제거된 과거 개념 예:

```text
BM25
HybridSearcher
RRF
File Corpus Loader
Separate Reranker
```

검색:

```bash
grep -RHnE \
'rag\.reranker|RerankResult|HybridSearcher|hybrid_search|bm25_search|reciprocal_rank_rank_fusion|load_corpus' \
backend pipeline rag config docs run_pipeline.py \
--include='*.py' \
--include='*.md' \
--exclude-dir='__pycache__' \
|| true
```

현재 Runtime Source of Truth:

```text
rag/db_pipeline.py
```

입니다.

---

# 56. 삭제한 파일 Import가 남아 있음

증상:

```text
ImportError
ModuleNotFoundError
```

전체 검색:

```bash
grep -RHn \
'삭제한모듈명' \
backend pipeline rag config run_pipeline.py \
--include='*.py' \
--exclude-dir='__pycache__'
```

수정 후:

```bash
python -m compileall
```

로 확인합니다.

---

# 57. Python Compile Test

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

# 58. Chat 기능 문제 진단 최단 경로

```text
POST /api/chat
      ↓
Evidence 있음?
```

## 없음

```text
Retrieval 확인
```

## 있음

```text
Evidence 내용 정확?
```

### 아니오

```text
Chunk / Embedding / Retrieval
```

### 예

```text
Answer 정상?
```

#### 아니오

```text
Generation
```

#### 예

```text
Backend/RAG 정상
Frontend 표시 확인
```

---

# 59. 공고 목록 문제 진단 최단 경로

```text
GET /api/announcements
```

## curl 실패

```text
Backend / DB
```

## curl 성공

```text
Frontend / Proxy
```

---

# 60. Frontend Chat 문제 진단 최단 경로

```text
Browser Chat 실패
      ↓
curl POST /api/chat
```

## curl 실패

```text
Backend/RAG
```

## curl 성공

```text
Frontend
```

이 순서를 지키면 디버깅 시간이 크게 줄어듭니다.

---

# 61. 서버 로그가 너무 길 때

최근 부분만 확인:

```bash
command 2>&1 | tail -100
```

예:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
... 2>&1 | tail -120
```

단 Stack Trace의 시작 부분이 잘릴 수 있으므로
필요하면 전체 로그도 확인합니다.

---

# 62. curl 결과가 너무 길 때

JSON formatting 도구가 있다면 사용합니다.

예:

```bash
curl -s \
http://127.0.0.1:8000/api/announcements \
| python -m json.tool
```

Chat:

```bash
curl -s \
-X POST \
http://127.0.0.1:8000/api/chat \
-H 'Content-Type: application/json' \
-d '{"announcementId":1,"question":"신청 일정은 언제인가?"}' \
| python -m json.tool
```

단 Server가 JSON이 아닌 500 Traceback을 반환하면 `json.tool`이 실패합니다.

그때는 먼저:

```text
curl -i
```

를 사용합니다.

---

# 63. `Expecting value`가 나오면 먼저 curl -i

잘못된 순서:

```text
500 Response
↓
python -m json.tool
↓
Expecting value
```

정상 디버깅 순서:

```text
curl -i
↓
HTTP Status 확인
↓
Content-Type 확인
↓
Raw Body 확인
↓
JSON일 때만 json.tool
```

---

# 64. Model Response Raw 확인

Generation이 이상할 때 `GeneratedAnswer`에는
Raw Response가 포함될 수 있습니다.

확인 목적:

```text
LLM이 실제로 무엇을 생성했는지
Generator가 무엇을 후처리했는지
```

를 분리합니다.

Raw LLM Response가 이미 이상하다면:

```text
LLM / Prompt
```

문제입니다.

Raw는 정상인데 최종 Answer가 이상하다면:

```text
Generator / Validation / 후처리
```

문제입니다.

---

# 65. Backend가 200을 반환하면 모든 것이 정상이라는 뜻은 아님

예:

```json
{
  "answer": "fallback",
  "grounded": true,
  "evidence": [...]
}
```

이 경우:

```text
Transport/API는 정상
Generation 품질은 비정상
```

입니다.

HTTP Status와 Application 품질을 구분합니다.

---

# 66. `grounded=true`의 의미를 과대해석하지 않기

`grounded=true`는 현재 구현상
근거 Source가 존재하는 상태와 관련됩니다.

다음을 보장하지 않습니다.

```text
답변 문장이 완벽함
LLM Generation 성공
검색 1위가 최적임
```

Evidence와 Answer를 함께 봅니다.

---

# 67. API Response 내부 Evidence가 너무 큼

현재 Chat Response는 Top-K Source Content를 반환하므로
Response가 길 수 있습니다.

이것은 현재 MVP 구조상 정상일 수 있습니다.

향후 최적화 가능:

```text
Evidence 요약
필요 Source만 반환
Content 길이 제한
Source Detail 별도 API
```

하지만 API 계약을 변경할 경우 Frontend도 함께 확인해야 합니다.

---

# 68. DB 검색 Score가 0.5~0.6 정도임

Dense Embedding Similarity Score는 절대적인 정답 확률이 아닙니다.

중요한 것은:

```text
동일 Corpus 내 상대적 Ranking
실제 검색 내용
```

입니다.

Score 하나만 보고 Retrieval 실패라고 판단하지 않습니다.

---

# 69. 동일 질문을 여러 번 했는데 LLM 답변이 달라짐

Generation randomness에 영향을 주는 설정:

```text
temperature
top_p
```

현재 안정성 목적 설정:

```text
temperature = 0.0
top_p = 1.0
```

정확한 현재 값:

```text
rag/generation/config.py
```

를 확인합니다.

---

# 70. Prompt Token이 너무 많음

LLM Response Usage에서 Prompt Token이 큰 경우:

```text
Context Top-K
Chunk 길이
Prompt instruction 길이
```

를 확인합니다.

관련:

```text
rag/generation/config.py
rag/generation/context_builder.py
rag/generation/prompt_builder.py
```

---

# 71. FastAPI Process에서 BGE-M3를 매 요청마다 로드하는 것 같음

현재 RAG Service에서는 Pipeline을 Cache하는 구조를 사용합니다.

관련:

```text
rag/service.py
```

`lru_cache` 기반 Pipeline 재사용 여부를 확인합니다.

FastAPI Process를 재시작하면 모델은 다시 로드될 수 있습니다.

---

# 72. 첫 Chat 요청이 느림

가능한 이유:

```text
BGE-M3 최초 Model Load
CUDA Warm-up
Model Cache Load
llama.cpp Initial Prompt Processing
```

두 번째 요청이 빨라진다면 초기화 비용일 수 있습니다.

---

# 73. GPU Memory가 부족함

확인:

```bash
nvidia-smi
```

가능한 대응:

```text
Embedding FP16
Batch Size 감소
불필요한 Model 동시 Loading 제거
Generation Model Size 조정
```

현재 Runtime에는 별도 Reranker Model을 사용하지 않으므로
불필요한 Reranker Model을 다시 로드하지 않습니다.

---

# 74. 프로젝트 정리 후 갑자기 Import가 깨짐

가능한 원인:

```text
삭제한 Legacy Module 참조
__init__.py Export
Dynamic Import
README가 아니라 실제 코드 참조
```

확인:

```bash
PYTHONPATH=. \
/home/ubuntu/ddokbot/venvs/one-cycle-backend/bin/python \
-m compileall -q \
backend pipeline rag config
```

그리고 실제 주요 Module Import를 테스트합니다.

---

# 75. 디버깅할 때 하지 말아야 할 것

다음 방식은 피합니다.

```text
한 오류 때문에 여러 계층 동시에 수정

500인데 Frontend부터 수정

Evidence가 정확한데 Embedding부터 재생성

DB 인증 오류인데 RAG Prompt 수정

Frontend 오타인데 Pipeline 재실행

파일이 안 쓰이는 것 같다고 Reference 확인 없이 삭제
```

---

# 76. 표준 문제 해결 순서

```text
1. 증상을 재현한다.
2. HTTP/CLI 결과를 그대로 확인한다.
3. 문제 계층을 분류한다.
4. 해당 계층의 Source of Truth를 본다.
5. 최소 수정한다.
6. 해당 계층만 먼저 테스트한다.
7. 상위 연결을 테스트한다.
8. 전체 Smoke Test 한다.
```

---

# 77. Source of Truth 빠른 표

| 문제 | 먼저 볼 파일 |
|---|---|
| Backend 실행 | `backend/app/main.py` |
| API Route | `backend/app/api/routes/` |
| API Schema | `backend/app/schemas/` |
| DB 연결 | `backend/app/db/session.py` |
| DB 구조 | `backend/app/models/` |
| Pipeline 실행 | `run_pipeline.py` |
| Pipeline Path | `config/paths.py` |
| Persistence | `backend/app/services/pipeline_persistence.py` |
| Query Embedding | `rag/retrieval/query_embedding.py` |
| Retrieval | `rag/db_pipeline.py` |
| Generation | `rag/generation/` |
| RAG Entry | `rag/service.py` |
| User API Base | `frontend/user/src/config.ts` |
| User Proxy | `frontend/user/vite.config.ts` |
| User Chat UI | `DetailScreen.tsx` |
| Admin Proxy | `frontend/admin/serve_admin.py` |

---

# 78. AI에게 Troubleshooting을 맡길 때

최소 다음을 함께 전달합니다.

```text
문제 증상

실행 명령

전체 Error Message

HTTP Status

Response Body

관련 Source File

README.md

docs/TROUBLESHOOTING.md
```

RAG라면:

```text
docs/RAG.md
```

DB라면:

```text
docs/DATABASE.md
```

Frontend라면:

```text
docs/FRONTEND.md
```

도 같이 전달합니다.

---

# 79. 좋은 Troubleshooting 요청 예

```text
POST /api/chat 결과는 HTTP 200이다.

grounded=true이고 evidence에는
"2026년 7월 23일 오전 10시부터"라는 정확한 근거가 있다.

하지만 answer는 Generation fallback이다.

Retrieval은 정상으로 보고 Generation 계층만 분석해라.
API 계약은 변경하지 마라.

관련 로그와 rag/generation 파일은 아래와 같다.
```

이렇게 문제 범위를 구체적으로 전달하면
불필요한 수정이 줄어듭니다.

---

# 80. 핵심 요약

가장 중요한 진단 규칙:

```text
curl도 실패
→ Backend/DB/RAG

curl 성공 + Browser 실패
→ Frontend/Proxy

Evidence 없음
→ Retrieval

Evidence 틀림
→ Retrieval/Chunking

Evidence 정확 + Answer 틀림
→ Generation

DB Write 완료 + 새 데이터 검색 안 됨
→ Activation

Expecting value
→ JSON Parser 문제가 아니라
   먼저 HTTP Response 확인

500
→ Backend Traceback 확인

422
→ Request Schema 확인
```

문제를 해결할 때는 항상
**“처음 문제가 발생한 계층”**을 찾아 그 계층부터 수정합니다.
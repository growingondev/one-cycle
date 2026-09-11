# Backend Integration

> 기준 코드: **`develop@1c3b2e9fedf9be1fba14253ec7de2ed678521a45`**
>
> 검토 기준일: **2026-08-28**
>
> 목적: Crawler / Document Processing / RAG / PostgreSQL과 Backend API 사이의
> **현재 실제 연결(AS-IS)** 과 Docker 서비스 분리 후 필요한 **목표 경계(TO-BE)** 를
> 한 문서에서 구분하여 인수인계한다.
>
> 과거 통합 과정은 `docs/BACKEND_DB_INTEGRATION_HISTORY.md`를 참고한다.
>
> Runtime 실측은 별도 문서
> `docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md`의 기준 Commit 범위를 유지해서 읽는다.

---

# 1. 문서 읽는 기준

이 문서에서 가장 중요한 구분은 다음 두 가지다.

```text
AS-IS
= 현재 develop 소스가 실제로 호출하는 방식

TO-BE
= AWS Docker 운영안에서 분리하려는 목표 방식
```

둘을 섞어 읽으면 안 된다.

현재 `develop`에서 Docker Compose로 실제 구성된 핵심 서비스는:

```text
postgres
```

뿐이다.

현재 다음 서비스는 **별도 Docker 서비스로 구현되어 있지 않다.**

```text
backend
rag
document-worker
embedding
llm
nginx
```

`llama.cpp`는 현재 RAG가 HTTP로 호출하는 외부 Process/Server이며,
Repository의 현재 Compose 서비스라고 해석하면 안 된다.

---

# 2. 현재 통합 구조 한눈에 보기

## 2.1 현재 AS-IS

```text
User / Admin Frontend
        │
        │ HTTP /api/*
        ▼
Backend FastAPI
        │
        ├─ SQLAlchemy ──────────────► PostgreSQL + pgvector
        │
        ├─ Python import/importlib ─► Integration Service
        │                               │
        │                               ├─ Python import ─► Crawler
        │                               │
        │                               ├─ DB ───────────► PostgreSQL
        │                               │
        │                               └─ Python callable
        │                                      ▼
        │                                Document Processor
        │                                      │
        │                                      ├─ File
        │                                      ├─ subprocess Parser
        │                                      ├─ subprocess Normalizer
        │                                      ├─ subprocess Structure
        │                                      ├─ subprocess Chunking
        │                                      ├─ subprocess Embedding/BGE-M3
        │                                      └─ DB Persistence
        │
        └─ Python import/importlib ─► RAG
                                        │
                                        ├─ Python import ─► BGE-M3 Query Embedding
                                        ├─ SQLAlchemy/SQL ─► PostgreSQL + pgvector
                                        └─ HTTP ──────────► llama.cpp
```

즉 현재는 Backend / Integration / RAG / Document Processor가
Docker Service 간 HTTP 통신으로 분리되어 있지 않다.

---

# 3. 통신 방식 Matrix

| From | To | 현재 방식 | 현재 핵심 구현 |
|---|---|---|---|
| Frontend | Backend | HTTP | `/api/*` |
| Backend | PostgreSQL | DB / SQLAlchemy | `backend/app/db/session.py` |
| Backend | RAG | Python import/importlib | `RAG_ANSWER_FUNCTION` |
| Backend | Integration | Python import/importlib | `COLLECTION_RUNNER`, `ANNOUNCEMENT_RECOLLECTOR` |
| Backend | Document Processor | Python import/importlib | `DOCUMENT_REPROCESSOR` |
| Backend | Error Retry | Python import/importlib 예정 | `ERROR_RETRY_RUNNER` 미연결 |
| Collection Service | Crawler | HTTP job API | `crawler_client.py` → `crawler:8000` |
| Document Processor | 원본 문서 | File | `Document.storage_path` |
| Document Processor | Parser 등 | subprocess | Python child process |
| Document Processor | BGE-M3 | subprocess + 직접 Model Load | `pipeline/embedding` |
| Pipeline Persistence | PostgreSQL | DB / SQLAlchemy | `SessionLocal` |
| RAG | BGE-M3 | Python import + 직접 Model Load | `load_bge_m3_model()` |
| RAG | PostgreSQL | DB / SQLAlchemy + SQL | pgvector + keyword |
| RAG | llama.cpp | HTTP | `/v1/chat/completions` |

Docker 전환에서 가장 크게 바뀌는 것은:

```text
Backend → RAG
Backend → Document Worker
RAG → Embedding
Document Worker → Embedding
```

이다.

---

# 4. 현재 Gateway 환경변수 계약

현재 `.env.example`의 Pipeline/RAG 연결:

```env
RAG_ANSWER_FUNCTION=rag.service:answer_question

COLLECTION_RUNNER=backend.app.services.integration_service:collect_persist_and_process
ANNOUNCEMENT_RECOLLECTOR=backend.app.services.integration_service:recollect_persist_and_process
DOCUMENT_REPROCESSOR=pipeline.document_processor:reprocess_document

# ERROR_RETRY_RUNNER=
```

관련 파일:

```text
backend/app/services/chat_service.py
backend/app/services/pipeline_gateway.py
```

두 파일 모두 `os.getenv()`와 `importlib.import_module()`을 사용한다.

따라서 현재 연결은:

```text
환경변수
↓
"module.path:function_name"
↓
importlib
↓
동일 Python Runtime에서 callable 호출
```

방식이다.

## 4.1 중요한 `.env` 주의

`pipeline_gateway.py`와 `chat_service.py`는
Pydantic `Settings` 객체가 아니라 `os.getenv()`를 직접 사용한다.

따라서 Host에서 `.env` 파일이 존재한다는 사실만으로
이 값들이 자동으로 `os.environ`에 들어간다고 가정하면 안 된다.

Host 실행 시 예:

```bash
set -a
source .env
set +a

export PYTHONPATH=.

python -m uvicorn backend.app.main:app \
  --host 127.0.0.1 \
  --port 18000
```

Docker에서는 `env_file:` 또는 `environment:`로 명시적으로 전달하는 것이 안전하다.

---

# 5. 전체 신규 수집 통합 계약

관리자 Endpoint:

```text
POST /api/admin/announcements/collect
```

현재 실제 호출 순서:

```text
Admin Route
backend/app/api/routes/admin.py
↓
pipeline_gateway.collect_announcements()
↓
COLLECTION_RUNNER
↓
integration_service.collect_persist_and_process()
↓
collection_service.collect_and_persist()
↓
crawler_client.crawl_announcements()
↓
persist_collection_result()
↓
CollectionRun / Announcement / Document 저장
↓
analysis_document_ids
↓
integration_service.process_document_ids()
↓
pipeline_gateway.reprocess_document()
↓
DOCUMENT_REPROCESSOR
↓
pipeline.document_processor.reprocess_document()
↓
Document Processing
↓
성공 조건 확인
↓
publish_collection_run()
```

---

# 6. 전체 수집에서 자동 처리되는 Document

`persist_collection_result()`가 자동 분석 대상으로 넣는 조건:

```text
document_role == primary
AND
download_status == completed
```

반환 필드:

```text
analysis_document_ids
```

따라서 전체 수집 자동 처리 정책은:

| Document Role | DB 저장 | 자동 Processing |
|---|---:|---:|
| `primary` | O | completed일 때 O |
| `supporting` | O | X |
| `unknown` | O | X |

여기서 `supporting/unknown`이 **절대로 처리 불가능하다는 뜻은 아니다.**

관리자 수동 재처리와 `reprocess_document()` 자체에는
`document_role == primary` 강제 검증이 없다.

이 차이는 반드시 유지해서 이해한다.

---

# 7. 전체 수집 결과와 자동 Publish

`collect_persist_and_process()`의 Publish 조건:

```text
Collection status == success
AND
Document processing failed_count == 0
AND
유효한 collection_run_id
AND
publish_collection_run() validation 통과
```

실패 시:

```text
status = failed
publish.status = skipped 또는 failed
```

Publish 성공 시:

```text
system_state.active_collection_run_id
```

가 새 CollectionRun으로 전환된다.

Publish 실패는 Backend ErrorLog에 기록한다.

---

# 8. 전체 수집 API는 현재 Background Job이 아니다

현재:

```text
POST /api/admin/announcements/collect
↓
Route 함수 내부에서
collect_announcements()
↓
전체 수집 + 문서 처리 + Publish
```

가 직접 실행된다.

즉 현재 구현은:

```text
HTTP 요청
→ 작업 등록 후 즉시 반환
```

형태의 Queue/Background Job 구조가 아니다.

Response Schema 이름은 `ActionAcceptedResponse`지만,
현재 전체 수집 callable 자체는 요청 처리 흐름 안에서 동기적으로 실행된다.

따라서 Docker 분리 후 초기 단계에서 Worker를 HTTP 동기 호출로 바꾸는 경우:

```text
긴 HTTP Timeout
Connection 유지
중복 요청 방지
Backend Worker 점유
GPU 작업 직렬화
```

문제를 반드시 고려해야 한다.

2026-08-26 Runtime 검증에서는 전체 수집 + 처리에
약 34분 35초가 걸린 기록이 있다.

단, 이 시간은 `develop@476575c`에서 측정한 역사적 실측값이다.

---

# 9. 개별 공고 재수집 계약

Endpoint:

```text
POST /api/admin/announcements/{announcement_id}/recollect
```

현재 호출:

```text
Admin Route
↓
pipeline_gateway.recollect_announcement()
↓
ANNOUNCEMENT_RECOLLECTOR
↓
integration_service.recollect_persist_and_process()
↓
collection_service.recollect_and_persist()
↓
crawler_client.recollect_announcement()
↓
신규 Document 저장
↓
new_analysis_document_ids
↓
Document Processor
```

재수집은:

```text
동일 filename + 동일 checksum
```

이면 기존 Document를 재사용한다.

새로 저장된 문서 중:

```text
primary
+
download_status = completed
```

만 `new_analysis_document_ids`로 처리한다.

---

# 10. 개별 재수집과 Collection Publish의 차이

`recollect_persist_and_process()`는 현재
`publish_collection_run()`을 호출하지 않는다.

따라서 재수집 자체가:

```text
active_collection_run_id
```

를 다른 Collection으로 전환하지는 않는다.

다만 주의할 점이 있다.

재수집 대상 Announcement가 **이미 Active Collection 소속**이라면,
그 Announcement에 새 Document가 저장되고 새 ProcessingRun/ChunkSet이 활성화된 후
RAG 검색 조건에 들어올 수 있다.

반대로 비활성 Collection 소속 Announcement를 재수집해도
사용자 RAG는 `system_state.active_collection_run_id` 조건 때문에
그 Collection을 검색하지 않는다.

즉:

```text
"재수집은 Publish를 안 한다"
```

와

```text
"재수집 결과가 절대 사용자 검색에 반영되지 않는다"
```

는 같은 의미가 아니다.

---

# 11. 수동 Document 재처리 계약

Endpoint:

```text
POST /api/admin/documents/{document_id}/reprocess
```

현재 호출:

```text
Admin Route
↓
pipeline_gateway.reprocess_document(document_id)
↓
DOCUMENT_REPROCESSOR
↓
pipeline.document_processor.reprocess_document(document_id=...)
```

입력:

```text
document_id
```

현재 DB Context 조회 조건:

```text
Document.id == document_id
AND
Document.download_status == completed
```

반환 Context:

```text
announcement_key
announcement_db_id
document_db_id
filename
format
storage_path
```

중요:

```text
document_role == primary
```

조건은 여기 없다.

따라서 supporting/unknown 문서 ID도
`download_status=completed`이고 파일이 유효하면
관리자가 수동 재처리를 시도할 수 있는 현재 구조다.

Docker 분리 전에:

```text
수동 재처리도 primary만 허용할지
supporting을 향후 별도 처리할지
unknown을 관리자 검토 후 허용할지
```

정책을 확정하는 것이 좋다.

---

# 12. Document Processor 실제 순서

파일:

```text
pipeline/document_processor.py
```

현재 필수 처리 순서:

```text
1. DB Document Context 조회
2. storage_path 원본 File 확인
3. 실제 HWP/HWPX 내부 형식 판별
4. Parser
5. Normalizer
6. Structure
7. Verification
8. Chunking
9. Embedding
10. Pipeline Persistence
11. KeyInformation 7개 필드 추출
12. KeyInformation DB upsert
13. ProcessingRun Activation
```

소스 코드의 요약 순서:

```text
Parser
→ Normalizer
→ Structure / Verification
→ Chunk
→ Embedding
→ Persistence
→ KeyInformation extraction
→ upsert_key_information()
→ activate_processing_run()
```

---

# 13. Document Processor의 subprocess 경계

현재 다음 단계는 별도 Python subprocess로 실행된다.

```text
Parser
Normalizer
Structure
Chunking
Embedding
```

Document Processor는 child process 실행 시:

```text
cwd = PROJECT_ROOT
PYTHONPATH에 PROJECT_ROOT 추가
```

를 수행한다.

즉 Docker `document-worker`는 최소한 다음 의존성을 한 Runtime에서 가져야 한다.

```text
Python Pipeline Dependencies
Java/JVM
HWP/HWPX Parser JAR
Crawler Dependencies
원본 Document Volume
Pipeline Output Volume
CUDA/BGE-M3
DB 접근
```

단 Docker 운영 목표에서는 BGE-M3를 별도 Embedding Service로 분리하므로
최종 Worker는 직접 BGE를 GPU에 로딩하지 않는 방향이다.

---

# 14. Parser JAR 경계

정상 `document_processor.py` 경로는 다음 JAR를 명시적으로 사용한다.

```text
pipeline/parser/libs/hwp/hwplib-1.1.10.jar
pipeline/parser/libs/hwpx/hwpxlib-1.0.8.jar
```

따라서 Document Worker Dockerfile/Volume에서
이 파일들이 실제로 존재해야 한다.

Parser를 Document Processor 밖에서 직접 실행할 경우
Parser 내부 fallback 경로와 실제 Repository JAR 위치 차이가 있을 수 있으므로,
직접 Parser CLI를 운영 진입점으로 삼기 전에는 `docs/ENVIRONMENT.md`의
JAR 경로 주의를 함께 확인한다.

---

# 15. File / `storage_path` 계약

Document Processor는 DB의:

```text
Document.storage_path
```

를 실제 파일 위치로 사용한다.

처리 규칙:

```text
absolute path
→ 그대로 사용

relative path
→ PROJECT_ROOT / storage_path
```

그리고 최종적으로:

```text
source_path.is_file()
```

을 검사한다.

따라서 DB Row만 복사해도 문서 처리가 되는 것이 아니다.

반드시 실제 원본 파일이 같은 논리 경로에서 보여야 한다.

---

# 16. Docker에서 Document Volume이 중요한 이유

Docker 분리 후 Crawler/Worker가 문서를 저장하더라도
다음 두 기능이 파일에 접근한다.

```text
1. Document Worker 재처리
2. Backend 관리자 Document Download
```

현재 관리자 다운로드:

```text
GET /api/admin/documents/{document_id}/download
↓
Backend FastAPI
↓
FileResponse(path=storage_path)
```

이다.

따라서 Docker 목표에서 문서 파일을 Worker만 볼 수 있게 Mount하면
Backend의 현재 관리자 다운로드 Endpoint가 깨질 수 있다.

분리 전 반드시 하나를 선택해야 한다.

```text
A. Backend와 Document Worker가 같은 Document Volume을 공유
B. Backend가 Worker/Storage Service를 통해 다운로드
C. Object Storage 등 별도 저장계층으로 전환
```

현재 MVP와 가장 적은 변경으로 맞추려면
공유 Document Volume이 단순하다.

---

# 17. Pipeline Persistence 계약

주요 저장 대상:

```text
ProcessingRun
DocumentStructure
ChunkSet
Chunk
Embedding
```

Persistence 직후 새 ProcessingRun은:

```text
is_active = false
```

이다.

KeyInformation까지 성공한 뒤:

```text
activate_processing_run(processing_run_id)
```

을 호출한다.

이 설계 목적:

```text
새 처리 결과가 완전히 성공하기 전에
기존 정상 active 데이터가 사라지는 것을 방지
```

---

# 18. KeyInformation 실패 보호

KeyInformation 처리 중 실패하면 현재 코드가 새 ProcessingRun을:

```text
failed
is_active = false
```

상태로 남기도록 시도한다.

보호 대상:

```text
기존 active ProcessingRun
기존 정상 KeyInformation
```

따라서 새 재처리가 실패했다고
기존 서비스 가능 데이터를 즉시 비활성화하지 않는다.

---

# 19. Activation 실패 주의

`activate_processing_run()` 호출 자체에서 예외가 발생하면
Document Processor는 `stage="activation"` 실패를 반환한다.

현재 activation 예외 처리 블록에서는
KeyInformation 실패 처리와 달리
`mark_processing_run_failed()`를 다시 호출하지 않는다.

따라서 activation 실패 장애를 조사할 때는:

```text
ErrorLog
ProcessingRun.execution_status
ProcessingRun.is_active
KeyInformation.source_processing_run_id
```

를 함께 확인해야 한다.

---

# 20. ProcessingRun 시간값 주의

현재 Pipeline Persistence에서 새 ProcessingRun 생성 시:

```text
started_at = now
finished_at = now
```

를 같은 시점에 기록한다.

따라서 DB의 이 값만으로:

```text
Parser 시작
→ Embedding
→ KeyInformation
→ Activation
```

전체 wall-clock 처리 시간을 계산하면 안 된다.

실제 Pipeline 전체 실행시간 측정이 필요하면
Worker 레벨의 별도 시작/종료 timestamp가 필요하다.

---

# 21. Collection Publish 검증 계약

Service:

```text
backend/app/services/collection_publish_service.py
```

Publish는 내부에서 validation을 수행한다.

주요 조건:

```text
CollectionRun.status == success
Announcement 존재
failed_announcement_count == 0
선언된 Announcement count와 실제 count 일치
unknown Document 없음
```

`supporting`:

```text
Publish 검증에서 분석 필수 대상이 아님
```

`primary`:

```text
download_status == completed
active ProcessingRun 존재
execution_status == succeeded
verification_status == pass
active ChunkSet 존재
ChunkSet.status == completed
Chunk 수 정합
모든 Chunk completed
모든 Chunk에 정상 Embedding 존재
```

Embedding 조건:

```text
model_name == 현재 RAG Embedding Model
dimension == 1024
normalized == true
status == completed
embedding IS NOT NULL
```

---

# 22. metadata-only Announcement

Publish 검증은 primary HWP/HWPX가 없는 Announcement를:

```text
metadata-only announcement
```

로 허용한다.

즉:

```text
공고에 primary 문서가 없다는 이유만으로
Collection 전체 Publish가 무조건 실패하는 구조는 아니다.
```

반면 `unknown` Document가 있으면 Publish를 차단한다.

---

# 23. 사용자 Announcement 데이터 경계

사용자 Announcement 조회는:

```text
system_state.active_collection_run_id
```

를 기준으로 Active Collection만 노출한다.

관리자 API는 같은 Active Collection 제한을 사용하지 않고
운영 전체 데이터를 조회할 수 있다.

따라서:

```text
User API = 서비스 중인 Snapshot
Admin API = 운영/이력 데이터
```

로 이해한다.

---

# 24. Backend → RAG 현재 계약

Endpoint:

```text
POST /api/chat
```

Backend 내부:

```text
chat_service.answer_question_via_rag()
↓
RAG_ANSWER_FUNCTION
↓
rag.service:answer_question
```

입력:

```text
announcement_id
question
```

RAG 반환은:

```text
ChatResponse 객체
또는
ChatResponse로 검증 가능한 dict
```

여야 한다.

현재 `rag.service.answer_question()`은 dict를 반환한다.

---

# 25. 현재 RAG 실행 구조

```text
Backend FastAPI Process
↓ Python import
rag.service.answer_question()
↓
DBRAGPipeline
↓
BGE-M3 Query Embedding
↓
PostgreSQL Vector Search
+
PostgreSQL Keyword Search
↓
RRF Hybrid Fusion
↓
Generation
↓ HTTP
llama.cpp /v1/chat/completions
```

`rag.service._get_pipeline()`은:

```text
@lru_cache(maxsize=1)
```

를 사용하므로 **현재 Python Process 내부에서** RAG Pipeline과 BGE 모델을 재사용한다.

따라서 현재는 별도 RAG Server가 있는 것이 아니다.

---

# 26. RAG → Embedding 현재 계약

현재 별도 Embedding HTTP API가 없다.

`rag/db_pipeline.py`:

```text
pipeline.embedding.model_loader
↓
load_bge_m3_model()
```

을 직접 호출한다.

현재:

```text
RAG
→ Python import
→ BGE-M3 직접 Load
→ GPU
```

이다.

Docker 목표:

```text
RAG
→ HTTP
→ Embedding Service
→ GPU
```

는 아직 구현 전이다.

---

# 27. Document Embedding과 Query Embedding 설정 차이

Document Embedding:

```text
pipeline/embedding/config.py
```

주요 환경변수:

```text
EMBEDDING_MODEL_NAME
EMBEDDING_MODEL_PATH
EMBEDDING_USE_FP16
EMBEDDING_REQUIRE_CUDA
EMBEDDING_DEVICE_INDEX
```

RAG Query Embedding:

```text
rag/retrieval/config.py
```

에서는 현재:

```text
EMBEDDING_MODEL_NAME
EMBEDDING_MODEL_PATH
```

를 환경에서 읽지만 다음 값은 코드 기본 구성에서 고정되어 있다.

```text
use_fp16 = True
require_cuda = True
device_index = 0
```

따라서 현재 두 Embedding 경로의 설정 동작이 완전히 통일되어 있지 않다.

Docker Embedding Service 분리 시 하나의 Runtime 계약으로 통일해야 한다.

---

# 28. Embedding 데이터 계약

현재 RAG/Publish가 기대하는 핵심 계약:

```text
model_name = BAAI/bge-m3
dimension = 1024
normalized = true
```

Query Embedding도 shape:

```text
(1024,)
```

를 검사한다.

Docker Embedding API를 새로 만들 때
이 값은 Request/Response/DB Validation 전 구간에서 일관되어야 한다.

---

# 29. Hybrid Retrieval Top-K 주의

`.env.example`:

```env
RAG_DB_TOP_K=5
```

만 보고 현재 Chat Vector Search가 5개만 검색한다고 보면 안 된다.

현재 `DBRAGPipeline.ask()`는 Hybrid Search Config를 구성하고,
Hybrid Search가 Vector 검색 전에 일시적으로:

```text
pipeline.top_k = config.vector_top_k
```

로 덮어쓴다.

현재 Retrieval 기본:

```text
vector_top_k = 20
bm25_top_k = 20
hybrid_top_k = 20
rrf_k = 60
```

따라서 일반 Hybrid Chat 경로의 Vector 후보 수는 현재 기본 20이다.

`RAG_DB_TOP_K=5`는 DBRAGPipeline의 기본 `top_k` 초기값이지만
Hybrid 호출에서는 그대로 최종 검색 수가 되지 않는다.

---

# 30. RAG 검색 범위

Vector 검색은 다음 범위를 사용한다.

```text
system_state.active_collection_run_id
+
요청 announcement_id
+
active ChunkSet
+
active ProcessingRun
+
completed Chunk
+
completed Embedding
+
현재 Embedding Model
+
dimension = 1024
+
normalized = true
```

즉 DB에 Chunk가 있다는 사실만으로 검색되는 것이 아니다.

Active chain이 완성되어야 한다.

---

# 31. MVP RAG 제한 환경변수

현재:

```env
MVP_ANNOUNCEMENT_ID=1
MVP_DOCUMENT_FORMAT=hwpx
```

가 Template에 존재한다.

`MVP_ANNOUNCEMENT_ID`가 설정되면
다른 `announcement_id`에 대해 RAG가 지원하지 않는 공고 응답을 반환한다.

따라서 실제 Active Collection의 Announcement ID가 바뀐 환경에서는
Template 값 `1`을 그대로 운영값으로 사용하면 안 된다.

`MVP_DOCUMENT_FORMAT`은 Generation에 전달되는 대표 문서 형식 fallback 성격이다.

Docker 전환 전에 이 MVP 제한을 유지할지 제거할지 결정해야 한다.

---

# 32. RAG → LLM 현재 계약

현재 이 경계는 이미 HTTP다.

환경변수:

```env
LLAMA_BASE_URL=http://127.0.0.1:8080
```

실제 Endpoint:

```text
POST {LLAMA_BASE_URL}/v1/chat/completions
```

OpenAI-compatible payload를 사용한다.

따라서 Docker 전환 시 가장 작은 변경은:

```text
현재
http://127.0.0.1:8080

Docker 목표
http://llm:8080
```

처럼 Hostname을 Service Name으로 바꾸는 것이다.

---

# 33. RAG 오류의 HTTP 의미 주의

`chat.py`는 `RagServiceUnavailableError`일 때:

```text
HTTP 503
```

을 반환한다.

하지만 `rag.service.answer_question()`은
`pipeline.ask()` 내부 오류를 포괄적으로 잡아
다음과 같은 일반 답변 dict로 변환하는 경로가 있다.

```text
답변 생성 중 오류...
grounded = false
evidence = []
```

따라서 내부 RAG/Generation 오류가 발생했다고 해서
항상 `/api/chat`이 HTTP 5xx를 반환한다고 가정하면 안 된다.

Docker RAG Service API를 새로 정의할 때:

```text
정상적인 "근거 없음"
실제 Retrieval 장애
실제 Embedding 장애
LLM 장애
Service 장애
```

를 HTTP Status / Error Payload 관점에서 구분할지 결정해야 한다.

---

# 34. ErrorLog 통합

Integration Service의 `process_document_ids()`는
Document Processor 결과가 실패하거나 예외가 발생하면:

```text
backend.app.services.error_log_service.record_error()
```

를 호출한다.

현재 `record_error()` 결과에서 Integration Service가 읽는 Key:

```text
error_id
```

이다.

Stage → Error Type 매핑 예:

```text
parser            → parsing
normalizer        → normalizing
structure         → structuring
verification      → verification
chunking          → chunking
embedding         → embedding
persistence       → database
key_information   → database
activation        → database
```

---

# 35. 수동 Document 재처리 ErrorLog 주의

전체 수집/재수집:

```text
integration_service.process_document_ids()
```

를 통과하므로 실패 결과를 ErrorLog에 기록한다.

하지만 관리자 수동 재처리:

```text
Admin Route
→ pipeline_gateway.reprocess_document()
→ document_processor.reprocess_document()
```

는 `process_document_ids()`를 통과하지 않는다.

현재 `run_document_reprocess()` Route 자체도
`success=False` 결과를 ErrorLog로 다시 기록하지 않는다.

따라서 수동 재처리 실패가:

```text
항상 Integration ErrorLog에 자동 기록된다
```

고 가정하면 안 된다.

Docker Worker API 설계 때 ErrorLog 책임 주체를 하나로 정해야 한다.

예:

```text
A. Worker가 실패를 DB ErrorLog에 직접 기록
B. Backend가 Worker 실패 응답을 받아 기록
C. 중앙 Job/Queue 계층이 기록
```

중복 기록되지 않도록 한 곳을 기준으로 정하는 것이 좋다.

---

# 36. Error Retry 현재 상태

Endpoint:

```text
POST /api/admin/errors/{error_id}/retry
```

Gateway:

```text
pipeline_gateway.retry_error()
↓
ERROR_RETRY_RUNNER
```

하지만 현재 `.env.example`:

```text
# ERROR_RETRY_RUNNER=
```

상태다.

따라서:

```text
Endpoint 존재
≠
실제 Retry Pipeline 연결 완료
```

다.

현재는 `PipelineUnavailableError` → HTTP 503 경로를 예상해야 한다.

---

# 37. Admin Action Endpoint의 현재 동기/응답 주의

다음 Endpoint는 Route 내부에서 callable을 직접 실행한다.

```text
POST /api/admin/announcements/collect
POST /api/admin/announcements/{id}/recollect
POST /api/admin/documents/{id}/reprocess
POST /api/admin/errors/{id}/retry
```

현재 `collect`는 반환 result의:

```text
status == failed
```

를 확인하여 HTTP 500으로 바꾸는 코드가 있다.

반면 `recollect`와 `document reprocess`는
Pipeline callable이 dict를 반환한 뒤
그 내부 실패 상태를 항상 HTTP 5xx로 변환하는 구조가 아니다.

특히 Document Reprocess는:

```text
reference.success = false
```

가 포함된 `ActionAcceptedResponse`가 반환될 수 있다.

Frontend/운영 자동화에서:

```text
HTTP 201 == 실제 처리 성공
```

으로 단순 해석하지 않는 것이 안전하다.

Docker Worker API를 만들 때 이 계약도 정리해야 한다.

---

# 38. 현재 PostgreSQL 통합

현재 `infra/docker-compose.yml`에서
실제로 정의된 핵심 Service:

```text
postgres
```

Image:

```text
pgvector/pgvector:0.8.2-pg16
```

Host Bind:

```text
127.0.0.1:${POSTGRES_PORT:-5432}:5432
```

Persistent Data:

```text
Docker named volume
one-cycle-postgres-data
```

따라서 현재 Host Process들은 일반적으로:

```text
127.0.0.1:5432
```

을 통해 접근한다.

---

# 39. 현재 Runtime 검증 — 범위 구분

`docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md`는:

```text
develop@476575c
```

기준 AWS 실측 문서다.

그 당시 확인된 결과:

```text
CollectionRun ID        2
Announcement           50
Document               86
primary                48
supporting             38
unknown                 0

Processing success     48 / 48
Chunk                  13,863
Embedding              13,863

dimension              1024
normalized             true

active_collection_run_id
1 → 2
```

Backend/Admin core tests:

```text
48 / 48 PASS
```

전체 실행시간:

```text
약 34분 35초
```

이 값들은 **현재 `develop@1c3b2e9`를 새로 Runtime 검증한 결과가 아니다.**

현재 HEAD에는 이후 변경이 더 포함되어 있으므로
인수인계 문서에서 이 수치를 "현재 최신 HEAD 실측"으로 적으면 안 된다.

---

# 40. 현재 HEAD의 검증 표현 원칙

현재 문서 기준 Source는:

```text
develop@1c3b2e9fedf9be1fba14253ec7de2ed678521a45
```

이다.

Source Code 계약은 현재 HEAD 기준으로 확인한다.

Runtime 숫자는:

```text
2026-08-26
develop@476575c
```

범위로만 사용한다.

현재 HEAD 전체 Runtime PASS를 증명하려면
동일 Commit을 AWS에 반영한 뒤 테스트/E2E를 다시 실행해야 한다.

---

# 41. Docker 운영 목표 TO-BE

AWS Docker 운영안의 목표 서비스:

```text
services
├─ nginx
├─ backend
├─ rag
├─ document-worker
├─ embedding
├─ llm
└─ postgres
```

Queue:

```text
초기 제외
```

향후 필요 시:

```text
Backend
↓
Queue
↓
Document Worker
```

로 확장한다.

이 구조는 현재 구현이 아니라 **목표 구조**다.

---

# 42. Docker 목표 구조

```text
User / Admin
     │
     ▼
   Nginx
     │
     ▼
  Backend
   │  │
   │  ├──────────────► PostgreSQL
   │  │
   │  ├──────────────► RAG Service
   │  │                   │
   │  │                   ├─► Embedding Service
   │  │                   ├─► PostgreSQL
   │  │                   └─► LLM Service
   │  │
   │  └──────────────► Document Worker
   │                      │
   │                      ├─► Embedding Service
   │                      ├─► PostgreSQL
   │                      └─► Shared Document Storage
```

---

# 43. Docker 분리 시 바뀌는 경계

## 43.1 Backend → RAG

현재:

```text
Python import/importlib
rag.service:answer_question
```

목표:

```text
HTTP
Backend → rag Service
```

필요 계약:

```text
Endpoint
Request Schema
Response Schema
Timeout
Health Check
HTTP Status
Error Payload
Grounded / No Evidence 의미
```

Frontend의 기존 `ChatRequest / ChatResponse` 계약을 최대한 유지하면
Frontend 변경을 줄일 수 있다.

---

# 44. Backend → Document Worker

현재:

```text
Python callable
```

목표:

```text
Backend
→ Document Worker Service 경계
```

초기 Queue는 사용하지 않는다.

따라서 초기 구현 선택지는 사실상:

```text
동기 HTTP 호출
또는
간단한 Job API + Worker 내부 Background 실행
```

중 하나가 된다.

현재 Full Collection 실측 시간이 수십 분이므로
단순 동기 HTTP를 선택하면 Timeout/재시도/중복 실행 정책이 필수다.

---

# 45. RAG → Embedding

현재:

```text
Python import
BGE-M3 직접 Load
```

목표:

```text
HTTP
RAG → embedding Service
```

최소 Query API 계약:

```text
input:
  text

output:
  model_name
  dimension
  normalized
  vector
```

유지해야 할 핵심 값:

```text
BAAI/bge-m3
1024
normalized = true
```

실제 Endpoint 이름/Port/Schema는 아직 Repository에서 확정된 것이 아니다.

---

# 46. Document Worker → Embedding

현재:

```text
Document Processor
↓ subprocess
pipeline/embedding/run_embeddings.py
↓
BGE-M3 직접 Load
```

목표:

```text
Document Worker
↓ HTTP
Embedding Service
```

문서 배치 Embedding 계약에서 최소 확인:

```text
입력 Chunk 순서
chunk_id
embedding_text
batch size
model version
dimension
normalized
vector 순서
부분 실패 처리
timeout
```

Document Embedding과 Query Embedding이 같은 Model Runtime을 사용하도록 통일하는 것이
Docker 분리의 핵심 목적 중 하나다.

---

# 47. RAG → LLM

현재부터 이미 HTTP다.

현재:

```text
127.0.0.1:8080
```

Docker 목표:

```text
llm:8080
```

따라서 코드 구조 변경보다:

```text
Service DNS
Environment
Health Check
Startup order
Timeout
GPU 할당
```

정리가 핵심이다.

---

# 48. PostgreSQL Hostname 전환

현재 Host Process:

```text
POSTGRES_HOST=127.0.0.1
```

Docker 내부 목표:

```text
POSTGRES_HOST=postgres
```

Container 간에는 Compose Service Name을 hostname으로 사용한다.

운영 단계에서는 PostgreSQL 5432를 외부 인터넷에 공개하지 않는다.

---

# 49. Document Shared Volume 목표

AWS Docker 운영안 예:

```text
Host
/home/ubuntu/ddokbot/storage/documents

Container
/storage/documents
```

분리 전 반드시 확정:

```text
Crawler 저장 경로
Document Worker mount 경로
Backend download용 mount 경로
DB storage_path 저장 규칙
상대경로 vs 절대경로
기존 Row 변환 필요 여부
```

권장되는 핵심 원칙:

```text
DB에 Host 전용 절대경로를 무조건 저장하지 말 것
Container 간 동일하게 해석 가능한 경로 정책을 정할 것
```

---

# 50. Model Volume 목표

AWS Docker 운영안:

```text
Host
/home/ubuntu/ddokbot/models

Container
/models
```

Embedding 예:

```text
Host
/home/ubuntu/ddokbot/models/embedding/bge-m3

Container
/models/embedding/bge-m3
```

LLM 예:

```text
Host
/home/ubuntu/ddokbot/models/llm/gemma4-12b

Container
/models/llm/gemma4-12b
```

모델은 Image에 포함하지 않는 운영 목표다.

---

# 51. PostgreSQL Persistent Storage 전환 주의

현재:

```text
one-cycle-postgres-data
```

Named Volume을 사용한다.

Docker 운영안에는 향후:

```text
/home/ubuntu/ddokbot/storage/postgres
```

Bind Mount도 검토 대상으로 적혀 있다.

이것은 현재 구현이 아니다.

Named Volume → Bind Mount 전환 전에 반드시:

```text
Backup
Data Copy 검증
DB Owner/Permission
pgvector 확인
Alembic Version 확인
Rollback
```

을 준비한다.

---

# 52. Docker Port — 확정/미확정 구분

운영안에서 비교적 일관된 값:

```text
nginx      80 / 443
backend    18000
llm        8080
postgres   5432
```

운영안 문서 내부에서 RAG/Embedding은 예시가 충돌한다.

한 위치:

```text
embedding  8001
rag        8002
```

다른 표:

```text
rag        18001
embedding  18002
```

따라서 현재 인수인계 기준:

```text
RAG internal port       미확정
Embedding internal port 미확정
```

최종 Source of Truth는 실제 구현될:

```text
infra/docker-compose.yml
```

로 통일한다.

---

# 53. Nginx 목표

현재 개발 단계에서 Nginx는
Repository의 실행 중 Compose 서비스라고 볼 수 없다.

운영 목표:

```text
Internet
↓ HTTPS :443
Nginx
↓
Backend :18000
```

역할:

```text
HTTPS
SSL
Reverse Proxy
API Routing
Timeout
Request Size
외부 Port 최소화
```

Document upload/download나 긴 API가 존재하면
Nginx timeout과 body/file 설정도 함께 검토한다.

---

# 54. GPU 서비스 목표

AWS Docker 운영안의 목표는 NVIDIA L4 1개를:

```text
embedding
llm
```

중심으로 공유하는 구조다.

목표 상태에서는:

```text
RAG가 BGE 직접 Load하지 않음
Document Worker가 BGE 직접 Load하지 않음
```

으로 만들어 GPU Model 중복 로딩을 줄인다.

현재 AS-IS는 이 상태가 아니다.

현재 RAG와 Document Embedding 경로는 각각 직접 BGE-M3를 로드할 수 있다.

---

# 55. 현재 GPU 운영 정책과 코드 조건 구분

과거 AWS 운용에서는 GPU 자원 충돌을 피하기 위해
문서 재처리 시 llama.cpp를 내리고 작업한 기록이 있다.

이것은:

```text
운영 절차
```

이지 현재 Source Code가 강제하는 Lock/스케줄러가 아니다.

Docker로 나눈다고 GPU 총량이 늘어나는 것이 아니므로:

```text
Embedding 동시 요청 수
LLM GPU Memory
Worker 동시성
CUDA OOM
```

을 별도로 관리해야 한다.

Queue는 초기 목표에서 제외되어 있으므로
초기 Compose에서는 최소한 실행 동시성 정책이 필요하다.

---

# 56. Evaluation DB와 Integration

평가 Workflow는 별도 DB:

```text
one_cycle_evaluation_tmp
```

를 사용한다.

평가 Pipeline도 기존 Document Processing/Integration 코드를 재사용한다.

Docker 분리 후 평가 실행 시에도:

```text
운영 DB
one_cycle

평가 DB
one_cycle_evaluation_tmp
```

를 혼동하면 안 된다.

특히 Worker/Backend Container 환경변수를 평가용으로 바꿀 때
운영 DB에 평가 Dataset을 저장하지 않도록 DB Guard를 유지한다.

상세:

```text
docs/BACKEND_DB_EVALUATION_WORKFLOW.md
```

---

# 57. Docker 분리 전에 반드시 정의할 Service API

아직 Source Code로 확정되지 않은 항목:

## RAG Service

```text
Health
Answer Question
```

결정:

```text
Request/Response
No Evidence
Internal Error
Timeout
LLM Error
Embedding Error
```

## Embedding Service

```text
Health
Query Embedding
Document Batch Embedding
```

결정:

```text
model identity
dimension
normalize
batch
max input length
timeout
GPU error
```

## Document Worker

```text
Health
Full Collection
Announcement Recollect
Document Reprocess
```

또는 Job 형태라면:

```text
Create Job
Get Job Status
Job Result
```

실제 Endpoint 이름은 아직 확정하지 않는다.

---

# 58. Error 처리 책임을 Docker에서 다시 정해야 하는 이유

현재는 같은 Python/DB 공간에서 여러 Module이 직접:

```text
record_error()
```

를 호출할 수 있다.

서비스 분리 후:

```text
Backend
RAG
Document Worker
Embedding
LLM
```

이 각자 실패할 수 있다.

반드시 정할 것:

```text
누가 ErrorLog를 DB에 기록하는가?
원격 Service Error를 누가 Backend Error Type으로 변환하는가?
중복 ErrorLog를 어떻게 막는가?
stack trace를 어느 서비스가 보관하는가?
HTTP 4xx/5xx와 DB ErrorLog 상태를 어떻게 연결하는가?
```

---

# 59. Health Check 분리

현재 Backend:

```text
/api/health
/api/health/db
```

가 있다.

Docker 목표에서는 Service별 최소 Health가 필요하다.

```text
backend
rag
embedding
llm
document-worker
postgres
```

단순 Process 생존과 실제 Ready 상태를 가능하면 구분한다.

예:

```text
embedding process up
≠
BGE model ready

llm process up
≠
GGUF model ready

rag process up
≠
embedding/DB/llm까지 모두 usable
```

---

# 60. Startup Dependency

Docker Compose의 `depends_on`만으로
AI Model이 실제 Ready임을 보장한다고 가정하면 안 된다.

예상 의존:

```text
postgres ready
↓
backend / rag / worker DB 사용 가능

embedding model ready
↓
rag query embedding 가능
↓
worker document embedding 가능

llm model ready
↓
rag generation 가능
```

Health/Retry 정책을 같이 설계한다.

---

# 61. Migration 소유권

현재 Alembic과 DB Model은 Backend Repository에 있다.

Docker 분리 시:

```text
누가 alembic upgrade head를 실행하는가?
```

를 명확히 정한다.

권장 원칙:

```text
여러 Container가 동시에 Migration 실행하지 않게 한다.
```

예:

```text
명시적 migration one-shot command
또는
배포 단계에서 1회 실행
```

Postgres Container init SQL과 Alembic 책임도 혼동하지 않는다.

---

# 62. 현재 자동화되지 않은 운영 위험

현재 구조에서 특히 주의:

```text
긴 Full Collection 동기 실행
ERROR_RETRY_RUNNER 미연결
수동 reprocess role guard 없음
수동 reprocess 실패 ErrorLog 경계 불완전
ProcessingRun wall-clock timestamp 부정확
RAG Query/Document Embedding 설정 차이
RAG_DB_TOP_K와 Hybrid Top-K 의미 차이
MVP_ANNOUNCEMENT_ID 제한
File storage_path의 Host/Container 경로 문제
RAG/Embedding Docker API 미정
RAG/Embedding Port 미정
GPU 동시성 제어 미구현
```

---

# 63. 장애 확인 순서 — 전체 수집

전체 수집 실패 시:

```text
1. Backend API 응답
2. COLLECTION_RUNNER 환경변수
3. Integration Service 결과
4. CollectionRun status
5. Crawler result / ErrorLog
6. analysis_document_ids
7. document_processing.failed_count
8. ErrorLog stage/error_code
9. ProcessingRun
10. ChunkSet / Chunk
11. Embedding
12. Publish result
13. system_state.active_collection_run_id
```

---

# 64. 장애 확인 순서 — Document Processing

```text
1. Document.download_status == completed ?
2. Document.storage_path 존재 ?
3. 실제 File 존재 ?
4. DB format과 실제 내부 HWP/HWPX 일치 ?
5. Parser JAR 존재 ?
6. Java 실행 가능 ?
7. Normalizer output 생성 ?
8. Verification pass ?
9. Chunk output 생성 ?
10. BGE/CUDA 실행 가능 ?
11. Embedding metadata/vector 정합 ?
12. ProcessingRun 생성 ?
13. KeyInformation 7개 필드 성공 ?
14. ProcessingRun activation 성공 ?
```

---

# 65. 장애 확인 순서 — Chat/RAG

```text
1. POST /api/chat 도달 ?
2. RAG_ANSWER_FUNCTION 환경변수 ?
3. MVP_ANNOUNCEMENT_ID 제한 ?
4. BGE-M3 Query Model Load 가능 ?
5. CUDA 가능 ?
6. system_state.active_collection_run_id 존재 ?
7. 요청 Announcement가 Active Collection 소속 ?
8. active ProcessingRun 존재 ?
9. active ChunkSet 존재 ?
10. completed Chunk / Embedding 존재 ?
11. model_name/dimension/normalized 일치 ?
12. Hybrid Vector Search ?
13. Keyword Search ?
14. RRF 결과 존재 ?
15. LLAMA_BASE_URL 접근 가능 ?
16. /v1/chat/completions 응답 정상 ?
```

---

# 66. Docker 전환 Preflight Checklist

코드 변경 전에:

```text
[ ] 현재 AWS pwd 확인
[ ] Git branch / commit 확인
[ ] 현재 Postgres backup
[ ] Named Volume 확인
[ ] .env 실제 전달 방식 확인
[ ] BGE Model 실제 Host 경로 확인
[ ] GGUF 실제 Host 경로 확인
[ ] NVIDIA Container Toolkit 확인
[ ] Java/JAR 확인
[ ] Document 실제 저장 경로 확인
[ ] DB storage_path 표본 확인
```

계약:

```text
[ ] Backend → RAG HTTP 계약
[ ] Backend → Worker 계약
[ ] RAG → Embedding 계약
[ ] Worker → Embedding 계약
[ ] Error payload 공통 규칙
[ ] Health/Ready 규칙
[ ] Timeout
[ ] Retry
[ ] 중복 요청 방지
[ ] ErrorLog 책임
```

DB/File:

```text
[ ] Migration 실행 주체
[ ] postgres persistence
[ ] shared documents volume
[ ] backend download 접근
[ ] storage_path 규칙
[ ] pipeline output volume
```

GPU:

```text
[ ] embedding GPU 할당
[ ] llm GPU 할당
[ ] 동시 실행 정책
[ ] OOM 대응
```

---

# 67. 주요 Source 파일 Index

Backend API:

```text
backend/app/main.py
backend/app/api/router.py
backend/app/api/routes/admin.py
backend/app/api/routes/chat.py
```

Gateway:

```text
backend/app/services/pipeline_gateway.py
backend/app/services/chat_service.py
```

Collection / Integration:

```text
backend/app/services/collection_service.py
backend/app/services/integration_service.py
backend/app/services/collection_publish_service.py
backend/app/services/document_role_service.py
```

Persistence / DB:

```text
backend/app/db/session.py
backend/app/services/pipeline_persistence.py
backend/app/services/key_information_service.py
backend/app/services/error_log_service.py
```

Document Processing:

```text
pipeline/document_processor.py
pipeline/parser/
pipeline/normalizer/
pipeline/structure/
pipeline/chunking/
pipeline/embedding/
pipeline/key_information_extractor.py
```

RAG:

```text
rag/service.py
rag/db_pipeline.py
rag/retrieval/config.py
rag/retrieval/hybrid_search.py
rag/retrieval/keyword_search.py
rag/generation/config.py
rag/generation/llm_client.py
rag/generation/generator.py
```

Environment / Docker:

```text
.env.example
infra/docker-compose.yml
docs/ENVIRONMENT.md
AWS_Docker_운영.pdf
```

Runtime evidence:

```text
docs/BACKEND_DB_RUNTIME_VALIDATION_20260826.md
```

Evaluation:

```text
docs/BACKEND_DB_EVALUATION_WORKFLOW.md
```

---

# 68. 인수인계 핵심 요약

현재 Backend Integration의 핵심은 다음과 같다.

```text
Frontend → Backend
= HTTP

Backend → RAG
= Python import/importlib

Backend → Integration / Pipeline
= Python import/importlib

Collection → Crawler
= Python import

Document Processing 내부
= File + subprocess + Python + DB

RAG → BGE-M3
= Python import / 직접 GPU Load

RAG → PostgreSQL
= DB direct

RAG → llama.cpp
= HTTP

PostgreSQL
= 현재 실제 Docker Compose 서비스
```

전체 신규 수집:

```text
Crawler
→ DB 저장
→ primary + completed 처리
→ KeyInformation
→ ProcessingRun 활성화
→ Publish 검증
→ active_collection_run_id 전환
```

Docker 목표:

```text
Backend → RAG Service
Backend → Document Worker
RAG → Embedding Service
RAG → LLM Service
RAG → PostgreSQL
Document Worker → Embedding Service
Document Worker → PostgreSQL
```

초기 Docker 목표에는 Queue가 없다.

따라서 Docker 분리의 핵심은 단순히 Container 파일을 만드는 것이 아니라:

```text
현재 Python 함수 호출 계약을
서비스 간 명시적 계약으로 바꾸면서
기존 DB/File/RAG 의미를 보존하는 것
```

이다.

특히 다음 네 가지를 먼저 확정해야 한다.

```text
1. Backend ↔ RAG API
2. Backend ↔ Document Worker API/Job 방식
3. RAG/Worker ↔ Embedding API
4. Document storage_path / Shared Volume 정책
```

이 네 경계가 확정되면
현재 기능을 유지하면서 Docker 서비스 분리를 진행할 수 있다.

# Backend / DB Evaluation Workflow

> 목적: 운영 DB에 존재하지 않는 평가 문서를 임시 평가 DB에 적재하고,
> 운영 서비스와 동일한 문서 처리 / DB 저장 / Publish / RAG 검색 경로를
> 사용할 수 있도록 Backend / DB 실행 흐름을 구성한다.
>
> 구현 브랜치: `feature/evaluation-db-backend`

---

## 1. 작업 배경

RAG 평가 대상 문서는 운영 LH 수집 데이터에 포함되어 있지 않다.

평가 문서를 운영 DB에 직접 추가하면 실제 서비스 데이터와 평가 데이터가
섞이기 때문에 기존 PostgreSQL 인스턴스 안에 임시 평가 DB를 별도로 생성한다.

운영 DB:

```text
one_cycle
```

평가 DB:

```text
one_cycle_evaluation_tmp
```

두 DB는 데이터와 `system_state.active_collection_run_id`를 서로 독립적으로 관리한다.

---

## 2. 전체 평가 흐름

```text
평가 원본 HWP/HWPX
↓
임시 평가 DB 등록
↓
CollectionRun
↓
Announcement
↓
Document
↓
기존 Document Processing Pipeline
↓
Parser
↓
Normalizer
↓
Structure / Verification
↓
Chunking
↓
Embedding
↓
DB Persistence
↓
ProcessingRun / ChunkSet 활성화
↓
Publish
↓
평가 DB의 active Collection
↓
Vector Search + Keyword Search
↓
RRF
↓
LLM Generation
↓
평가 답변 + 검색 근거
```

최종적으로 평가 과정에서 다음 값을 사용할 수 있어야 한다.

```text
answer
retrieved_chunk_ids
retrieved_contexts
```

RAGAS Metric 계산은 별도 평가 단계에서 수행한다.

---

## 3. 운영 DB와 평가 DB 분리

운영 Backend:

```text
POSTGRES_DB=one_cycle
```

평가 Backend:

```text
POSTGRES_DB=one_cycle_evaluation_tmp
```

평가 DB에서 Publish를 수행해도 변경되는 것은

```text
one_cycle_evaluation_tmp.system_state
```

뿐이다.

운영 DB인 `one_cycle`의 active Collection에는 영향을 주지 않는다.

---

## 4. 구현 파일

### 4.1 평가 문서 등록

```text
backend/app/services/evaluation_service.py
```

역할:

```text
평가 원본 파일
↓
CollectionRun 생성
↓
Announcement 생성
↓
Document 생성
```

기존 Backend의

```python
persist_collection_result()
```

를 재사용한다.

실제 LH Crawler는 실행하지 않는다.

Crawler가 수행하던 DB 등록 부분만 평가 원본에 맞게 연결한다.

평가 Backend에는 특정 GC / BD 문서가 하드코딩되어 있지 않다.

등록 시 필요한 값:

```text
dataset_id
evaluation_document_id
source_path
document_format
```

따라서 다른 평가 문서도 같은 방식으로 등록할 수 있다.

---

### 4.2 평가 Pipeline / Publish

```text
backend/app/services/evaluation_pipeline_service.py
```

역할:

```text
평가 Collection의 primary Document 조회
↓
process_document_ids()
↓
기존 reprocess_document()
↓
전체 처리 성공 확인
↓
publish_collection_run()
```

하나의 평가 문서라도 처리에 실패하면 Publish하지 않는다.

성공 시 다음 정보를 반환한다.

```text
collection_run_id
announcement_id
document_id
processing_run_id
chunk_set_id
chunk_count
embedding_count
embedding_model_name
```

---

### 4.3 평가 DB 생성

```text
backend/scripts/evaluation/create_evaluation_db.py
```

수행 과정:

```text
one_cycle_evaluation_tmp 생성
↓
pgvector 활성화
↓
Alembic upgrade head
↓
vector / alembic_version 검증
```

실행:

```bash
python backend/scripts/evaluation/create_evaluation_db.py
```

---

### 4.4 평가 DB 삭제

```text
backend/scripts/evaluation/drop_evaluation_db.py
```

평가 종료 후 임시 평가 DB만 삭제한다.

삭제 대상은 다음 DB로 제한한다.

```text
one_cycle_evaluation_tmp
```

운영 DB인 `one_cycle`은 삭제 대상이 아니다.

실행:

```bash
python backend/scripts/evaluation/drop_evaluation_db.py
```

---

## 5. 평가 원본과 storage_path

평가 원본은 기존 프로젝트 위치를 그대로 사용한다.

예:

```text
evaluation/source_documents/
├─ DOC_GC_001/
│  └─ v1/
│     └─ *.hwpx
└─ DOC_BD_001/
   └─ v1/
      └─ *.hwpx
```

프로젝트 내부 파일은 DB의 `Document.storage_path`에
프로젝트 상대경로로 저장한다.

예:

```text
evaluation/source_documents/DOC_GC_001/v1/example.hwpx
```

따라서 프로젝트 Root가 달라도 동일한 경로 구조를 사용할 수 있다.

```text
Windows
C:\Project\one-cycle

AWS
/home/ubuntu/ddokbot/one-cycle
```

기존 `reprocess_document(document_id)`가
`Document.storage_path`를 읽어 실제 원본을 처리한다.

---

## 6. DB 안전장치

평가 등록 및 평가 Pipeline은 다음 DB에서만 실행할 수 있다.

```text
one_cycle_evaluation_tmp
```

두 단계로 확인한다.

### 설정값 확인

```text
settings.postgres_db
```

### 실제 연결 DB 확인

```sql
SELECT current_database();
```

둘 중 하나라도 `one_cycle_evaluation_tmp`가 아니면 실행을 중단한다.

이를 통해 실수로 운영 DB에 평가 데이터를 등록하거나
평가 Pipeline을 실행하는 것을 방지한다.

---

## 7. Local DB Runtime 검증

Windows Local 환경에서 평가 DB 생성을 실제 확인했다.

결과:

```text
database created: one_cycle_evaluation_tmp
pgvector enabled
alembic upgrade head 완료
alembic version: 3d70b82ff082
```

DB 상태:

```text
one_cycle
- public tables: 15
- announcements: 50

one_cycle_evaluation_tmp
- public tables: 15
- announcements: 0
```

운영 DB와 평가 DB가 분리되어 생성된 것을 확인했다.

---

## 8. 평가 문서 등록 Runtime 검증

GC 평가 원본 1건을 실제 평가 DB에 등록했다.

결과:

```text
collection_run_id: 1
announcement_id: 1
document_id: 1
evaluation_document_id: DOC_GC_001
document_role: primary
download_status: completed
document_format: hwpx
```

DB 관계:

```text
CollectionRun 1
└─ Announcement 1
   └─ Document 1
```

`storage_path`도 실제 평가 원본 경로로 정상 등록됐다.

---

## 9. Local Pipeline Runtime 검증

등록된 평가 Document를 기존 Pipeline으로 실행했다.

```python
reprocess_document(document_id=1)
```

결과:

```text
HWPX Parser       PASS
Normalizer        PASS
Structure         PASS
Verification      PASS
Chunking          PASS
Embedding         STOP
```

GC 문서 Chunk 결과:

```text
총 Chunk: 207
```

Chunk 유형:

```text
intro: 7
paragraph_group: 40
paragraph_split: 1
table_fallback: 18
table_record: 141
```

Embedding 단계에서는 Local Windows 환경에서 CUDA를 사용할 수 없어 중단됐다.

```text
error_code: EMBEDDING_FAILED
stage: embedding
CUDA를 사용할 수 없습니다.
```

현재 Embedding Pipeline은 AWS GPU 사용을 전제로 하며
CPU fallback으로 자동 전환하지 않는다.

따라서 Embedding 이후 전체 Runtime 검증은 AWS에서 수행한다.

---

## 10. Backend 테스트 결과

신규 테스트:

```text
tests/backend/test_evaluation_services.py
```

결과:

```text
5 passed
```

검증 항목:

```text
운영 DB에서 평가 등록 차단
운영 DB에서 평가 Pipeline 실행 차단
실제 연결 DB 불일치 차단
문서 처리 실패 시 Publish 차단
문서 처리 성공 시 Publish 연결
```

관련 기존 Backend 테스트까지 포함한 결과:

```text
18 passed
```

대상:

```text
test_evaluation_services.py
test_integration_service.py
test_collection_publish_service.py
```

전체 Backend 테스트 결과:

```text
71 passed
4 failed
```

실패 4건은 기존 `KeyInformationExtractor` 테스트다.

이번 작업에서는 다음 파일을 수정하지 않았다.

```text
backend/app/services/key_information_extractor.py
tests/backend/test_key_information_extractor.py
```

`origin/develop` 대비 변경사항이 없음을 별도로 확인했다.

---

## 11. AWS에서 남은 E2E 검증

Local에서는 CUDA가 없어 Embedding 이후를 완료하지 못했다.

AWS GPU 환경에서 다음 흐름을 최종 검증한다.

```text
평가 DB 생성
↓
평가 문서 등록
↓
Document Processing
↓
Embedding
↓
DB Persistence
↓
ProcessingRun 활성화
↓
ChunkSet 활성화
↓
Publish
↓
평가 Backend 실행
↓
/api/chat
↓
Vector Search
↓
Keyword Search
↓
RRF
↓
LLM Generation
↓
answer
↓
retrieved_chunk_ids
↓
retrieved_contexts
```

GC와 BD 모두 이 흐름이 성공해야 최종 E2E 완료로 판단한다.

---

## 12. 평가 종료 후 정리

평가가 끝나면:

```text
평가 Backend 종료
↓
one_cycle_evaluation_tmp 삭제
```

운영 DB:

```text
one_cycle
```

는 그대로 유지한다.

평가 원본 문서와 평가 코드 역시 삭제 대상이 아니다.

---

## 13. 현재 상태

```text
평가 DB 생성                    완료
pgvector / Migration            완료
운영 DB 격리                    완료
평가 Document 등록              완료
기존 Pipeline 연결              완료
Processing 실패 Publish 차단    완료
평가 DB 삭제 기능               완료
Local Parser~Chunk Runtime       완료
Backend 관련 테스트             완료
AWS GPU Embedding 이후 E2E      미검증
Hybrid Search / LLM 평가        미검증
평가 결과 Excel 생성            미검증
```

현재 Backend / DB 연결 코드는 준비된 상태이며,
남은 핵심 작업은 AWS GPU 환경에서 실제 평가 문서를 대상으로
Embedding → Publish → Hybrid Search → LLM까지 Runtime 검증하는 것이다.

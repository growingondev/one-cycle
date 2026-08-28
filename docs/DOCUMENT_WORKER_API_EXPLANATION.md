# Document Worker API 구현 설명

## 1. 개요

기존 DDOKBOT MVP에서는 Backend, 문서처리, RAG가 하나의 Python 실행 환경 안에서 직접 import와 함수 호출 방식으로 연결되어 있었다. 문서처리 역시 Backend가 `pipeline/document_processor.py`의 함수를 직접 호출하는 방식으로 동작했다.

API/Docker 서비스 분리 버전에서는 이 구조를 유지하지 않고, 기능별로 독립된 Service Container를 구성한다. 이 과정에서 Backend와 문서처리 영역은 서로 다른 서비스가 되므로 직접 Python 함수를 호출할 수 없고, HTTP API를 통해 통신해야 한다.

이번 작업에서는 기존 문서처리 코드를 새로 작성하거나 교체하지 않고, 기존 Parser, Normalizer, Structure, Chunking 로직을 그대로 재사용하면서 이를 HTTP 요청으로 실행할 수 있도록 Document Worker API 계층을 추가했다.

현재 Document Worker는 Backend로부터 문서 정보를 전달받아 원본 파일을 확인하고, 실제 HWP/HWPX 형식을 판별한 뒤 Parser → Normalizer → Structure / Verification → Chunking까지 수행한다. Embedding은 별도 Service로 분리하기로 했기 때문에 현재 Worker 내부에서 직접 실행하지 않는다.

---

## 2. 서비스 분리 이후 Document Worker의 역할

서비스 분리 이후 전체 구조에서 Document Worker는 문서를 처리하는 전용 서비스 역할을 담당한다.

Backend는 문서의 DB Context와 ProcessingRun, Persistence를 관리하고, Document Worker는 실제 문서처리만 담당한다. 따라서 Worker는 Backend DB를 직접 조회하거나 저장하지 않는다. Backend가 필요한 정보를 HTTP Request로 전달하면 Worker는 해당 정보를 바탕으로 문서를 처리하고 결과 Artifact의 위치와 처리 결과를 반환한다.

Document Worker 내부에서는 Parser, Normalizer, Structure, Chunking을 각각 별도의 API로 나누지 않는다. 이 단계들은 같은 Container 내부에서 실행되므로 기존 Python 실행 구조를 그대로 사용할 수 있다.

반면 Embedding은 별도 Container에서 실행되기 때문에, 이후 Worker가 Embedding을 수행할 때는 직접 모델을 로드하지 않고 `POST /v1/embeddings` API를 호출해야 한다.

전체적인 책임 분리는 다음과 같다.

```text
Backend
- Document DB Context 조회
- Worker 호출
- Artifact 검증
- DB Persistence
- Key Information DB 저장
- ProcessingRun 관리

Document Worker
- 원본 문서 검증
- 실제 HWP/HWPX 형식 판별
- Parser
- Normalizer
- Structure / Verification
- Chunking
- Embedding Service 호출
- Key Information Extraction
```

---

## 3. Document Worker API 구조

이번 작업에서 새롭게 추가한 코드는 `document_worker` 디렉터리에 구성했다.

```text
document_worker/
├─ main.py
├─ service.py
└─ api/
   ├─ routes.py
   └─ schemas.py
```

`main.py`는 Document Worker용 FastAPI 애플리케이션을 생성하는 진입점이다. 여기에서 Router를 등록하고 Uvicorn으로 실행할 수 있도록 `app` 객체를 만든다.

`api/schemas.py`는 Backend와 Worker 사이에서 사용하는 Request와 Response 형식을 정의한다. Backend가 어떤 필드를 보내야 하는지, Worker가 최종적으로 어떤 값을 반환해야 하는지를 Pydantic 모델로 고정한다.

`api/routes.py`는 실제 HTTP Endpoint를 정의한다. 현재 구현된 Endpoint는 다음과 같다.

```http
POST /v1/documents/{document_id}/process
```

이 Endpoint가 호출되면 Request Body를 검증한 뒤 `service.py`의 `process_document()` 함수로 전달한다.

`service.py`는 실제 문서처리 흐름을 담당한다. 원본 파일 검증부터 Chunking까지 현재 구현된 모든 처리 단계가 이 파일에서 순서대로 연결된다.

---

## 4. Backend에서 Worker로 전달하는 정보

Backend는 DB에서 Document Context를 조회한 뒤 Worker에 다음 정보를 전달한다.

```json
{
  "announcement_id": 1,
  "announcement_key": "announcement_001",
  "source": {
    "filename": "announcement.hwpx",
    "format": "hwpx",
    "storage_path": "/data/documents/announcement_001/announcement.hwpx"
  }
}
```

`document_id`는 Request Body가 아니라 URL Path Parameter로 전달한다.

예를 들어 `document_id`가 1이라면 실제 요청 주소는 다음과 같다.

```http
POST /v1/documents/1/process
```

`announcement_id`는 해당 문서가 어느 공고에 속하는지를 나타내며 Chunking 단계에서도 사용한다.

`announcement_key`는 Artifact 출력 경로를 구분하기 위해 사용한다.

`source.filename`은 원본 파일명이고, `source.format`은 Backend가 알고 있는 문서 형식이다.

`source.storage_path`는 Worker가 실제로 접근해야 하는 원본 파일 경로다. Docker 환경에서는 Backend와 Worker가 `/data/documents`를 Shared Volume으로 사용하기 때문에 동일한 경로를 바라보게 된다.

---

## 5. 원본 문서 검증

문서처리를 시작하면 가장 먼저 `storage_path`에 실제 파일이 존재하는지 확인한다.

파일이 존재하지 않는데 Parser부터 실행하면 이후 오류가 Parser 문제인지 경로 문제인지 구분하기 어려워진다. 그래서 Worker는 처리 시작 시점에 파일 존재 여부를 먼저 검사한다.

파일을 찾지 못하면 다음과 같은 Error Response를 반환한다.

```json
{
  "error": {
    "code": "DOCUMENT_SOURCE_NOT_FOUND",
    "message": "원본 문서 파일을 찾을 수 없습니다."
  }
}
```

이 단계가 통과해야 실제 문서 형식 판별로 넘어간다.

---

## 6. 실제 HWP/HWPX 형식 판별

DDOKBOT 문서처리에서는 파일 확장자만 보고 HWP와 HWPX를 구분하지 않는다.

파일명이 `.hwp`여도 실제 내부 형식이 HWPX일 수 있고, 반대로 확장자와 실제 내부 구조가 맞지 않는 파일도 존재할 수 있기 때문이다.

그래서 Worker는 기존 `pipeline/parser/format_detector.py`의 `detect_actual_document_format()`을 재사용한다.

이 함수는 파일 내부 구조를 확인한 뒤 다음 중 하나를 반환한다.

```text
hwp
hwpx
unknown
```

그 다음 Backend가 Request로 전달한 `source.format`과 실제 판별 결과를 비교한다.

예를 들어 Backend가 `hwpx`라고 전달했고 실제 파일 내부도 HWPX라면 정상적으로 Parser 단계로 진행한다.

반대로 Backend는 `hwp`라고 전달했지만 실제 내부가 HWPX라면 형식 불일치 오류로 처리한다.

이 검증을 추가한 이유는 잘못된 Parser를 선택해 처리 실패가 발생하는 것을 막기 위해서다.

---

## 7. Parser 연결

실제 문서 형식이 확인되면 기존 Parser를 실행한다.

HWP 문서는 다음 코드를 사용한다.

```text
pipeline/parser/hwp_parser.py
```

HWPX 문서는 다음 코드를 사용한다.

```text
pipeline/parser/hwpx_parser.py
```

기존 문서처리 구현과 동일하게 subprocess 방식으로 Parser를 실행한다.

HWP Parser는 `hwplib-1.1.10.jar`를 사용하고, HWPX Parser는 `hwpxlib-1.0.8.jar`를 사용한다.

Parser 결과는 다음 경로에 저장된다.

```text
outputs/<announcement_key>/document_<document_id>/01_parsed/<format>.json
```

예를 들어 `announcement_key`가 `announcement_001`, `document_id`가 1, 실제 형식이 HWPX라면 다음 파일이 생성된다.

```text
outputs/announcement_001/document_1/01_parsed/hwpx.json
```

Worker는 subprocess가 정상 종료됐다는 사실만으로 성공 처리하지 않고, Parser 결과 JSON이 실제로 생성됐는지까지 확인한다.

---

## 8. Normalizer 연결

Parser가 생성한 JSON은 바로 Structure 단계로 넘기지 않고 기존 Normalizer를 거친다.

사용하는 코드는 다음과 같다.

```text
pipeline/normalizer/document_normalizer.py
```

입력은 Parser 결과다.

```text
01_parsed/hwpx.json
```

정규화가 끝나면 다음 위치에 결과가 생성된다.

```text
02_normalized/hwpx.json
```

Normalizer는 Parser 결과에 포함된 텍스트와 문자 표현을 후속 처리에 적합한 형태로 정리한다. 기존 문서처리에서 사용하던 정규화 로직을 그대로 재사용했기 때문에 API 분리 작업으로 인해 문서처리 품질 기준이 달라지지 않는다.

Normalizer 실행 이후에도 Worker는 결과 파일 존재 여부를 확인하고, 파일이 생성되지 않았다면 정상 처리로 넘기지 않는다.

---

## 9. Structure / Verification 연결

Normalizer 결과는 기존 Structure Pipeline으로 전달된다.

실행 파일은 다음과 같다.

```text
pipeline/structure/run_structure.py
```

Structure 단계에서는 문서 계층 구조화, 도메인 태깅, 표 세부 구조화, 값 타입 정규화와 검증이 순차적으로 수행된다.

실행 과정에서 여러 중간 산출물이 생성되지만 Worker가 후속 단계에서 중요하게 확인하는 결과는 다음 두 파일이다.

```text
step4-1_value_normalized.json
step4-3_verification.json
```

`step4-1_value_normalized.json`은 최종적으로 정리된 Structure 결과이며 다음 Chunking 단계의 입력으로 사용된다.

`step4-3_verification.json`은 최종 Structure 검증 결과다.

출력 경로는 다음과 같다.

```text
outputs/<announcement_key>/document_<document_id>/
└─ 03_structured/
   └─ <format>/
      ├─ step4-1_value_normalized.json
      └─ step4-3_verification.json
```

Worker는 Structure 실행 후 이 두 파일이 실제 존재하는지 확인한다.

---

## 10. Chunking 연결

Structure가 완료되면 최종 Structure 결과를 Chunking 단계에 전달한다.

사용하는 코드는 다음과 같다.

```text
pipeline/chunking/run_chunking.py
```

입력 파일은 다음과 같다.

```text
03_structured/<format>/step4-1_value_normalized.json
```

Chunking 결과는 다음 위치에 저장된다.

```text
04_chunks/<format>/chunks.json
```

Chunking 단계에서는 하나의 긴 공고문을 RAG 검색에서 사용할 수 있는 여러 개의 작은 단위로 분할한다.

각 Chunk는 이후 Embedding Service로 전달되고, 최종적으로 PostgreSQL과 pgvector에 저장되어 Retrieval에 사용된다.

Chunking 실행 시 `announcement_id`도 함께 전달한다. 이를 통해 생성된 Chunk가 어느 공고에 속하는지 구분할 수 있다.

Worker는 Chunking 실행이 끝난 뒤 `chunks.json`이 실제 생성됐는지도 확인한다.

---

## 11. 현재 생성되는 Artifact 구조

현재까지 구현된 Document Worker API를 정상 실행하면 다음 구조의 Artifact가 생성된다.

```text
outputs/
└─ <announcement_key>/
   └─ document_<document_id>/
      ├─ 01_parsed/
      │  └─ <format>.json
      ├─ 02_normalized/
      │  └─ <format>.json
      ├─ 03_structured/
      │  └─ <format>/
      │     ├─ step4-1_value_normalized.json
      │     ├─ step4-2_value_validation.json
      │     ├─ step4-3_verification.json
      │     └─ 기타 Structure 중간 산출물
      └─ 04_chunks/
         └─ <format>/
            └─ chunks.json
```

API 분리 전에도 사용하던 기존 Artifact 구조를 최대한 유지하도록 구성했다.

이 구조를 유지하면 이후 Backend Persistence 로직을 분리할 때도 기존 Artifact를 기준으로 DB에 저장할 수 있다.

---

## 12. Embedding을 Worker 내부에서 직접 실행하지 않는 이유

Embedding은 Document Worker와 별도의 Service로 분리한다.

따라서 기존처럼 Worker 프로세스 안에서 `pipeline/embedding/run_embeddings.py`를 직접 실행하는 구조로 연결하지 않는다.

최종 구조는 다음과 같다.

```text
Document Worker
    ↓
Chunking 완료
    ↓ HTTP
POST /v1/embeddings
    ↓
Embedding Service
    ↓
BGE-M3 실행
```

Embedding Service는 Document Worker뿐 아니라 RAG의 Query Embedding에서도 함께 사용한다.

즉 BGE-M3 모델을 한 서비스에 모아두고, Document Worker와 RAG가 동일한 HTTP API를 호출하는 구조다.

현재 Document Worker에서는 Chunking까지 구현되어 있으며, Embedding Service Endpoint가 준비되면 `chunks.json`의 Chunk 데이터를 읽어 `POST /v1/embeddings`로 전달하는 연동 작업이 추가될 예정이다.

---

## 13. 현재 501 응답을 유지한 이유

현재 Swagger에서 문서처리를 실행하면 Parser, Normalizer, Structure, Chunking까지 정상적으로 완료된 뒤 최종적으로 `501 Not Implemented`가 반환된다.

현재 단계에서는 이것이 의도된 동작이다.

Document Worker의 최종 성공 Response 계약에는 `embedding_count`와 7개의 `key_information`이 포함되어야 한다.

하지만 현재 Embedding Service 연동과 Key Information Extraction 연결이 아직 완료되지 않았다.

이 상태에서 임의로 `embedding_count=0`을 넣거나 빈 Key Information을 만들어 `200 completed`를 반환하면 실제 처리 완료 상태와 API 계약이 일치하지 않게 된다.

그래서 현재 `service.py`에서는 Chunking 성공 이후 다음 단계가 아직 구현되지 않았다는 사실을 명확하게 나타내기 위해 임시 `NotImplementedError`를 유지하고 있다.

현재 메시지는 다음 의미를 가진다.

```text
Document processing through chunking completed successfully.
Embedding service HTTP integration is pending.
```

즉 이 응답은 Chunking 실패를 의미하는 것이 아니라, **현재 구현 범위인 Chunking까지는 정상 완료됐고 그 이후 Service 연동이 아직 남아 있다는 의미**다.

---

## 14. 로컬 테스트 결과

이번 작업에서는 실제 HWPX 공고문을 사용해 Swagger에서 Document Worker API를 호출했다.

테스트한 문서는 다음과 같다.

```text
(계약금1,000)청주지북_B1블록_공공분양주택_잔여세대_추가_입주자모집(선착순_동호지정)_공고문.hwpx
```

테스트 과정에서 먼저 존재하지 않는 `/data/documents/announcement.hwpx` 경로를 전달해 `DOCUMENT_SOURCE_NOT_FOUND` 오류가 정상 반환되는 것을 확인했다.

그 다음 실제 Windows 로컬 파일 경로를 전달해 원본 파일 확인과 실제 HWPX 형식 판별이 정상 동작하는 것을 확인했다.

이후 기존 Parser가 실행되어 다음 파일이 생성되는 것을 확인했다.

```text
01_parsed/hwpx.json
```

Normalizer 실행 후에는 다음 파일이 생성됐다.

```text
02_normalized/hwpx.json
```

Structure Pipeline 실행 후에는 다음 주요 산출물이 정상 생성됐다.

```text
03_structured/hwpx/step4-1_value_normalized.json
03_structured/hwpx/step4-3_verification.json
```

마지막으로 Chunking을 연결해 다음 파일까지 생성되는 것을 확인했다.

```text
04_chunks/hwpx/chunks.json
```

따라서 현재 API 요청 한 번으로 원본 문서 확인부터 Chunking까지 기존 문서처리 Pipeline이 순서대로 실행되는 것을 확인한 상태다.

---

## 15. 기존 `pipeline/document_processor.py`와의 차이

기존 MVP의 `pipeline/document_processor.py`는 문서처리 외에도 Backend 책임까지 함께 가지고 있었다.

기존 흐름에는 Document Context 조회, 문서처리, Embedding, DB Persistence, Key Information 저장, ProcessingRun 관리가 한 실행 흐름에 포함되어 있었다.

서비스 분리 이후에는 이 책임을 분리한다.

Backend는 DB Context와 Persistence, ProcessingRun 상태를 관리한다.

Document Worker는 실제 문서처리와 Key Information 추출만 담당한다.

Embedding은 별도 Embedding Service가 담당한다.

이렇게 분리하면 각 Container의 책임이 명확해지고, 다른 Service의 내부 Python 코드에 직접 의존하지 않아도 된다.

---

## 16. 기존 Pipeline 코드와의 관계

이번 API 작업은 기존 Pipeline을 다시 구현한 것이 아니다.

다음 기존 코드는 그대로 사용한다.

```text
pipeline/parser/
pipeline/normalizer/
pipeline/structure/
pipeline/chunking/
```

새로 만든 `document_worker`는 이 기존 문서처리 Pipeline 앞에 HTTP 인터페이스를 추가한 Service Layer다.

쉽게 표현하면 기존 `pipeline`이 실제 문서를 처리하는 엔진이라면, `document_worker`는 Backend가 그 엔진을 HTTP로 실행할 수 있도록 만든 입구에 해당한다.

따라서 이번 작업으로 기존 문서처리 품질 로직 자체가 바뀐 것은 아니다.

---

## 17. 최종적으로 완성될 흐름

Document Worker가 완성되면 처리 흐름은 다음과 같다.

```text
Backend
    ↓ HTTP
POST /v1/documents/{document_id}/process
    ↓
Document Worker
    ↓
원본 파일 확인
    ↓
실제 HWP/HWPX 형식 판별
    ↓
Parser
    ↓
Normalizer
    ↓
Structure / Verification
    ↓
Chunking
    ↓ HTTP
Embedding Service
    ↓
Embedding Artifact 생성
    ↓
Key Information Extraction
    ↓
최종 Worker Response
    ↓
Backend
    ↓
Artifact 검증 및 DB Persistence
    ↓
Key Information 저장
    ↓
ProcessingRun 처리
```

이 흐름이 완성되면 Backend와 Document Worker 사이에는 직접 Python import가 필요하지 않게 된다.

---

## 18. 현재 구현 상태와 다음 작업

현재 Document Worker FastAPI 애플리케이션과 `POST /v1/documents/{document_id}/process` Endpoint는 구현되어 있다.

Request Schema와 기본 Error Response 처리도 추가했다.

문서처리 부분에서는 원본 파일 검증, 실제 HWP/HWPX 형식 판별, Parser, Normalizer, Structure / Verification, Chunking까지 연결하고 실제 HWPX 파일로 실행 결과를 확인했다.

다음 단계에서는 별도로 구현되는 Embedding Service와 Document Worker를 HTTP로 연결해야 한다.

그 이후 Key Information Extraction을 Worker 흐름에 연결하고, 최종 `DocumentProcessResponse`를 반환하도록 수정하면 Document Worker Endpoint가 완성된다.

이후 Backend에서는 기존 직접 함수 호출 방식을 제거하고 Document Worker HTTP Client를 실제 Runtime에 연결한다.

---

## 19. 이번 작업에서 추가된 파일

이번 Document Worker API 작업에서 추가된 파일은 다음과 같다.

```text
document_worker/api/routes.py
document_worker/api/schemas.py
document_worker/main.py
document_worker/service.py
```

작업 브랜치는 다음과 같다.

```text
feature/document-worker-api
```

이번 작업의 범위는 Document Worker API를 생성하고 기존 문서처리 Pipeline을 Chunking까지 연결하는 것이다.

Embedding Service 구현과 Worker의 Embedding HTTP 연동은 별도 후속 작업으로 진행한다.

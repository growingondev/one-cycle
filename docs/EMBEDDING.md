# AI/RAG 코드리뷰 - Embedding

## 1. Embedding 개요

### 1.1 역할

Embedding 단계는 Chunking에서 생성된 `chunks.json`을 입력받아 각 Chunk의
`embedding_text`를 **BGE-M3 모델을 이용해 Dense Vector로 변환하고 파일로
저장하는 단계**이다.

전체 흐름은 다음과 같다.

    04_chunks/chunks.json
            ↓
    Chunk 데이터 로드
            ↓
    입력 데이터 검증
            ↓
    BGE-M3 모델 로드
            ↓
    embedding_text → Dense Vector
            ↓
    L2 Normalize
            ↓
    Vector 검증
            ↓
    05_embeddings/
     ├─ embeddings.npy
     ├─ metadata.json
     └─ embedding_report.json

현재 Embedding 코드에서 직접 확인되는 범위는 **임베딩 결과 파일
생성까지**이다.

현재 제공된 Embedding 코드에는 PostgreSQL, pgvector, SQLAlchemy를 이용해
결과를 DB에 직접 저장하는 처리가 없다.

### 1.2 주요 파일

    pipeline/embedding/
    ├─ config.py
    ├─ models.py
    ├─ input_loader.py
    ├─ validator.py
    ├─ model_loader.py
    ├─ embedding_generator.py
    ├─ output_writer.py
    └─ run_embeddings.py

각 파일의 역할은 다음과 같다.

  파일 역할                  
  -------------------------- -----------------------------------
  `config.py`                모델 및 Embedding 실행 설정
  `models.py`                Embedding 데이터 객체 정의
  `input_loader.py`          `chunks.json` 탐색 및 로드
  `validator.py`             입력 Chunk 및 생성 Vector 검증
  `model_loader.py`          BGE-M3 모델 및 실행 환경 로드
  `embedding_generator.py`   Dense Vector 생성 및 L2 Normalize
  `output_writer.py`         임베딩 결과 파일 저장
  `run_embeddings.py`        전체 Embedding 실행 Entrypoint

------------------------------------------------------------------------

# 2. 입력 데이터

## 2.1 입력 파일

Embedding이 직접 읽는 파일은 Chunking에서 생성된 `chunks.json`이다.

기본 구조는 다음과 같다.

    outputs/
    └─ announcement_*/
       └─ 04_chunks/
          ├─ hwp/
          │  └─ chunks.json
          └─ hwpx/
             └─ chunks.json

따라서 Chunking과 Embedding의 현재 연결 방식은 **파일 I/O**이다.

    Chunking
       ↓
    chunks.json 저장
       ↓
    File I/O
       ↓
    Embedding

HWP와 HWPX가 모두 존재하면 각각의 `chunks.json`을 별도 입력으로 처리할
수 있다.

## 2.2 입력 파일 탐색

`run_embeddings.py`에서 `--inputs`를 직접 지정할 수 있고, 생략하면
`outputs` 아래를 자동 탐색한다.

    resolve_input_paths()
            ↓
    --inputs 지정?
       ├─ YES → 지정한 chunks.json 사용
       └─ NO
           ↓
       discover_chunk_files()
           ↓
    outputs/announcement_*/04_chunks/{hwp,hwpx}/chunks.json

중복된 입력 경로는 한 번만 사용하며, 최종 입력 파일이 없으면
`ChunkLoadError`가 발생한다.

## 2.3 실제 임베딩 대상

`chunks.json` 전체를 모델에 입력하는 것은 아니다.

현재 모델에 전달되는 필드는:

    TEXT_FIELD="embedding_text"

이다.

즉:

    Chunk
     ├─ chunk_id
     ├─ content
     ├─ search_text
     ├─ embedding_text  ← BGE-M3 입력
     └─ ...

형태이다.

------------------------------------------------------------------------

# 3. 입력 로드 및 데이터 구조

## 3.1 `input_loader.py`

`chunks.json`을 읽어 Embedding에서 사용할 Python 객체로 변환한다.

    chunks.json
        ↓
    _read_json()
        ↓
    chunks[]
        ↓
    chunk_id / embedding_text 추출
        ↓
    metadata 구성
        ↓
    EmbeddingItem[]
        ↓
    LoadedChunkDocument

`_read_json()`에서는 다음을 확인한다.

-   파일 존재 여부
-   실제 파일 여부
-   정상 JSON 여부
-   JSON 최상위 값이 객체인지 여부

`load_chunk_document()`에서는 각 Chunk의 `chunk_id`와 `embedding_text`를
읽고 나머지 정보를 Metadata로 구성한다.

-   `-limit`이 지정된 경우 앞쪽 N개의 Chunk만 처리한다.

## 3.2 데이터 모델

`models.py`에서는 크게 두 객체를 사용한다.

### `EmbeddingItem`

하나의 Embedding 대상 Chunk이다.

    EmbeddingItem
    ├─ chunk_id
    ├─ embedding_text
    └─ metadata

### `LoadedChunkDocument`

하나의 `chunks.json`을 읽은 결과이다.

    LoadedChunkDocument
    ├─ source_path
    ├─ document
    ├─ chunking
    └─ items[]

추가로 다음 값을 제공한다.

    chunk_count
    document_id
    announcement_id

## 3.3 Metadata

기존 Chunk 정보는 `_copy_metadata()`를 통해 Metadata로 유지된다.

주요 정보는 다음과 같다.

    vector_index

    chunk_id
    document_id
    announcement_id

    chunk_order
    chunk_type

    section_id
    section_level
    section_path

    title
    normalized_title
    search_title

    content
    search_text

    domain
    source

    token_count
    char_count

    source_filename
    source_format
    source_chunk_file

`announcement_id`는 우선:

    chunk.announcement_id

를 사용하고, 없으면:

    document.announcement_id

를 사용한다.

현재 코드에서 확인되는 흐름은:

    chunks.json
       ↓
    announcement_id
       ↓
    EmbeddingItem.metadata
       ↓
    metadata.json

까지이다.

------------------------------------------------------------------------

# 4. 입력 데이터 검증

## 4.1 `validator.py`

모델 실행 전에 Chunk 데이터를 검증한다.

오류로 검사하는 주요 항목은:

-   Embedding 대상 Chunk 존재 여부
-   `chunk_id` 존재 여부
-   동일 파일 내부 `chunk_id` 중복 여부
-   `embedding_text` 존재 여부
-   `metadata.vector_index`와 실제 순서 일치 여부
-   Metadata와 `EmbeddingItem`의 `chunk_id` 일치 여부

다음은 Warning으로 처리한다.

-   `announcement_id` 없음
-   `document_id` 없음
-   `content` 없음
-   `search_text` 없음
-   `section_path`가 list가 아님

## 4.2 여러 입력 파일 검증

`validate_multiple_documents()`는 여러 `chunks.json`을 함께 검증한다.

같은 파일 안에서 동일한 `chunk_id`가 중복되면 오류지만, 서로 다른 입력
파일 간 동일한 `chunk_id`는 허용한다.

따라서 HWP/HWPX 결과가 각각 존재하더라도 별도 파일로 처리할 수 있다.

------------------------------------------------------------------------

# 5. BGE-M3 모델 설정 및 로드

## 5.1 기본 설정

`config.py`의 주요 기본값은 다음과 같다.

  설정 기본값    
  -------------- ------------------
  Model          `BAAI/bge-m3`
  Text Field     `embedding_text`
  Batch Size     `8`
  Max Length     `8192`
  FP16           `True`
  CUDA 필수      `True`
  GPU Index      `0`
  L2 Normalize   `True`

환경변수는 다음과 같다.

  환경변수 역할              
  -------------------------- ----------------
  `EMBEDDING_MODEL_NAME`     모델 이름
  `EMBEDDING_MODEL_PATH`     모델 로드 경로
  `EMBEDDING_USE_FP16`       FP16 사용 여부
  `EMBEDDING_REQUIRE_CUDA`   CUDA 필수 여부
  `EMBEDDING_DEVICE_INDEX`   GPU 번호

## 5.2 `model_loader.py`

모델 로드 흐름은 다음과 같다.

    load_bge_m3_model()
            ↓
    get_runtime_info()
            ↓
    CUDA 상태 확인
            ↓
    Device 결정
            ↓
    FlagEmbedding import
            ↓
    BGEM3FlagModel 생성
            ↓
    LoadedEmbeddingModel

사용 모델 객체는 `FlagEmbedding`의:

    BGEM3FlagModel

이다.

CUDA 사용 시 Device는:

    cuda:<device_index>

형태로 설정되며 GPU 이름과 총 메모리 정보도 확인한다.

기본적으로 CUDA가 필요하지만 실행 시:

    --allow-cpu

를 사용하면 CUDA 필수 조건을 해제할 수 있다.

## 5.3 모델 재사용

여러 입력 파일을 처리할 때 BGE-M3를 파일마다 다시 로드하지 않는다.

    전체 입력 Load / Validation
            ↓
    BGE-M3 Load 1회
            ↓
    Document 1
            ↓
    Document 2
            ↓
    Document 3
            ↓
    ...

------------------------------------------------------------------------

# 6. Dense Embedding 생성

## 6.1 `embedding_generator.py`

실제 Vector 생성의 핵심 함수는:

    generate_embeddings()

이다.

입력은:

    LoadedEmbeddingModel
    EmbeddingItem[]
    batch_size
    max_length
    normalize_embeddings

이며 결과는:

    GeneratedEmbeddings
    ├─ vectors
    ├─ elapsed_seconds
    └─ normalized

형태이다.

## 6.2 BGE-M3 Encode

각 `EmbeddingItem`의 `embedding_text`를 추출하여 BGE-M3에 전달한다.

    EmbeddingItem[]
           ↓
    embedding_text[]
           ↓
    BGE-M3 encode()

현재 Encode 설정은:

    return_dense=Truereturn_sparse=Falsereturn_colbert_vecs=False

이다.

따라서 현재 생성하는 것은 **Dense Vector만**이다.

`dense_vecs`는 `numpy.float32` 배열로 변환되며 최종 형태는:

    (Chunk 수, Embedding 차원)

이다.

## 6.3 L2 Normalize

기본적으로 생성된 Dense Vector에 L2 Normalize를 적용한다.

    Vector
      ↓
    L2 Norm
      ↓
    Vector / Norm
      ↓
    Normalized Vector

기본값은 `True`이며:

    --no-normalize

옵션으로 비활성화할 수 있다.

## 6.4 Vector 검증

생성 후 다음 항목을 검사한다.

-   결과가 `numpy.ndarray`인지
-   2차원 배열인지
-   Chunk 수와 Vector 수가 같은지
-   Embedding 차원이 0보다 큰지
-   NaN 존재 여부
-   Infinity 존재 여부
-   Zero Vector 존재 여부

따라서 검증은:

    입력 Chunk 검증
           ↓
    Embedding 생성
           ↓
    생성 Vector 검증

두 단계로 이루어진다.

------------------------------------------------------------------------

# 7. 출력 데이터

## 7.1 출력 경로

`output_writer.py`는 입력 경로의:

    04_chunks

를:

    05_embeddings

로 변경하여 출력 위치를 결정한다.

예:

    입력

    outputs/announcement_001/
    └─ 04_chunks/
       └─ hwp/
          └─ chunks.json

    출력

    outputs/announcement_001/
    └─ 05_embeddings/
       └─ hwp/
          ├─ embeddings.npy
          ├─ metadata.json
          └─ embedding_report.json

## 7.2 `embeddings.npy`

BGE-M3가 생성한 Dense Vector 배열을 NumPy `.npy` 형식으로 저장한다.

    Vector Index 0 → Chunk 0
    Vector Index 1 → Chunk 1
    Vector Index 2 → Chunk 2
    ...

Vector는 `float32`로 저장된다.

## 7.3 `metadata.json`

Vector 순서와 원본 Chunk 정보를 연결하기 위한 Metadata 파일이다.

주요 구조는:

    schema_version
    생성 시간

    model
    ├─ name
    ├─ dimension
    ├─ normalized
    ├─ dtype
    ├─ device
    ├─ device_name
    └─ use_fp16

    source
    ├─ chunk_file
    ├─ document_id
    ├─ announcement_id
    └─ chunk_count

    items[]
    └─ 각 Chunk metadata

각 Item에는 `vector_index`와 `chunk_id`가 포함되어 Vector와 Chunk를
연결한다.

## 7.4 `embedding_report.json`

실행 결과 및 환경 정보를 저장한다.

주요 정보:

    status

    document_id
    announcement_id

    model_name

    device
    device_name
    torch_version
    cuda_version
    use_fp16
    gpu_memory_gb

    chunk_count
    embedding_count
    embedding_dimension
    embedding_dtype
    normalized

    batch_size
    max_length

    nan_count
    infinity_count
    zero_vector_count

    norm_statistics

    elapsed_seconds
    average_seconds_per_chunk

## 7.5 안전한 파일 저장

출력 파일은 바로 최종 파일에 덮어쓰지 않고 임시 파일을 이용한다.

    임시 파일 생성
        ↓
    데이터 저장
        ↓
    flush / fsync
        ↓
    최종 경로로 replace

NumPy와 JSON 출력 모두 이러한 방식으로 저장한다.

------------------------------------------------------------------------

# 8. 전체 실행 구조

## 8.1 `run_embeddings.py`

Embedding 전체 실행 Entrypoint이다.

    CLI 입력
       ↓
    Argument 검증
       ↓
    입력 파일 탐색
       ↓
    chunks.json Load
       ↓
    입력 Validation
       ↓
    BGE-M3 Load
       ↓
    Dense Embedding
       ↓
    Vector Validation
       ↓
    Output 저장
       ↓
    CUDA Cache 정리

## 8.2 주요 함수 호출 순서

    main()
     │
     ├─ parse_args()
     ├─ validate_arguments()
     ├─ resolve_input_paths()
     │   └─ discover_chunk_files()
     │
     ├─ load_multiple_chunk_documents()
     │   └─ load_chunk_document()
     │       ├─ _read_json()
     │       └─ _copy_metadata()
     │
     ├─ validate_multiple_documents()
     ├─ load_bge_m3_model()
     │   └─ get_runtime_info()
     │
     └─ Document별 반복
         ├─ generate_embeddings()
         │   ├─ model.encode()
         │   ├─ _extract_dense_vectors()
         │   ├─ _normalize_l2()
         │   └─ validate_embeddings()
         │
         ├─ write_embedding_outputs()
         │   ├─ resolve_output_directory()
         │   ├─ build_metadata_payload()
         │   ├─ build_report_payload()
         │   ├─ _write_numpy_atomic()
         │   └─ _write_json_atomic()
         │
         └─ clear_cuda_cache()

## 8.3 실행 옵션

주요 실행 옵션은 다음과 같다.

    --inputs
    → 특정 chunks.json 직접 지정

    --limit
    → 각 파일의 앞쪽 N개 Chunk만 처리

    --allow-cpu
    → CUDA 필수 조건 해제

    --no-normalize
    → L2 Normalize 비활성화

-   `-inputs`가 없으면 `outputs`를 자동 탐색한다.

------------------------------------------------------------------------

# 9. 다른 코드와의 연결

## 9.1 Chunking → Embedding

현재 연결은 파일 I/O다.

    Chunking
       ↓
    04_chunks/.../chunks.json
       ↓
    Embedding

## 9.2 Embedding 내부 연결

  ------------------------------------------------------------------------
  호출 대상 방식                                          
  --------------------------- --------------------------- ----------------
  `run_embeddings.py`         `input_loader.py`           Python import

  `input_loader.py`           `models.py`                 Python import

  `run_embeddings.py`         `validator.py`              Python import

  `run_embeddings.py`         `model_loader.py`           Python import

  `model_loader.py`           `FlagEmbedding`             Python Library

  `run_embeddings.py`         `embedding_generator.py`    Python import

  `embedding_generator.py`    BGE-M3                      Python 함수 호출

  `run_embeddings.py`         `output_writer.py`          Python import
  ------------------------------------------------------------------------

## 9.3 Backend ErrorLog 연결

`run_embeddings.py`에는:

    frombackend.app.services.error_log_serviceimportrecord_error

가 존재한다.

따라서 현재 연결은:

    Embedding
       ↓ Python import
    Backend ErrorLog Service

이다.

Embedding 예외 발생 시 `record_error()`를 이용해 오류 정보를 기록한다.

## 9.4 DB 연결 여부

현재 제공된 Embedding 코드에는 다음 동작이 없다.

    PostgreSQL INSERT
    pgvector INSERT
    SQLAlchemy Session 생성
    DB Repository 호출

따라서 현재 Embedding 코드에서 확인되는 최종 출력은:

    05_embeddings/
    ├─ embeddings.npy
    ├─ metadata.json
    └─ embedding_report.json

까지이다.

**`05_embeddings → DB`** **연결은 이 Embedding 코드만으로 확인할 수
없다.**

------------------------------------------------------------------------

# 10. 전체 데이터 흐름 요약

    [Chunking]

    04_chunks/
    └─ chunks.json
          │
          │ File I/O
          ▼
    ──────────────────────────────
            EMBEDDING
    ──────────────────────────────

    input_loader.py
          ↓
    LoadedChunkDocument
          ↓
    EmbeddingItem[]
          ↓
    validator.py
          ↓
    model_loader.py
          ↓
    BGE-M3
          ↓
    embedding_generator.py
          ↓
    Dense Vector
          ↓
    L2 Normalize
          ↓
    Vector Validation
          ↓
    output_writer.py

    ──────────────────────────────
              OUTPUT
    ──────────────────────────────

    05_embeddings/
    ├─ embeddings.npy
    ├─ metadata.json
    └─ embedding_report.json

한 문장으로 정리하면:

> **Chunking 결과인** **`chunks.json`에서 각 Chunk의**
> **`embedding_text`를 읽어 BGE-M3 Dense Vector를 생성하고, Vector·Chunk
> Metadata·실행 정보를** **`05_embeddings`에 파일로 저장한다.**

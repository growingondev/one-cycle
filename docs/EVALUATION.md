# RAG Evaluation

## 1. 목적

평가는 문서를 처리했다는 사실뿐 아니라 필요한 근거를 찾고, 근거에 맞는 답변을 생성하는지 확인합니다. 운영 DB와 분리된 평가 DB에서 실제 Pipeline과 RAG API를 사용합니다.

## 2. 평가 흐름

```text
평가 원본문서 등록
  → 실제 문서 처리·Embedding
  → 평가 CollectionRun Publish
  → 질문별 POST /api/chat
  → 답변과 Evidence 저장
  → Retrieval·Generation·Human 평가
```

## 3. 질문 유형

- 빈도가 높은 기본 질문
- 표현을 바꾼 질문
- 여러 조건이 포함된 질문
- 표와 문단을 함께 봐야 하는 어려운 질문
- 구어체 질문
- 문서에 답이 없는 질문
- 오탈자·노이즈가 있는 강건성 질문

## 4. 주요 평가 항목

| 구분 | 확인 내용 |
|---|---|
| Recall@K | 정답 근거가 검색된 상위 K개 안에 포함되는가 |
| Correct Rejection | 근거가 없는 질문을 억지로 답하지 않는가 |
| RAGAS | 답변의 사실성·관련성 등 자동 평가 |
| Human Score | 사람이 정답성·근거성·가독성을 확인 |
| Evidence | 반환 Chunk가 실제 원문 근거인가 |

## 5. 답변과 모범답안

평가 Sheet의 Reference 또는 모범답안과 서비스 답변을 비교합니다. 점수가 낮으면 다음 순서로 원인을 구분합니다.

1. 원문이 제대로 Parsing·Structure되었는가?
2. 정답 근거가 올바른 Chunk에 들어갔는가?
3. Vector·BM25·RRF 검색이 해당 Chunk를 찾았는가?
4. Prompt가 검색 근거를 올바르게 사용했는가?
5. LLM이 근거 밖의 내용을 생성했는가?

문서 처리 결과가 정상인데 답변이 잘못되면 Retrieval 설정 또는 Prompt·Generation 문제일 가능성이 큽니다.

## 6. 평가 DB 분리

평가 DB는 `one_cycle_evaluation_tmp`입니다. 평가 전용 Backend는 19000, RAG는 19002, Worker는 19003에 연결됩니다. 공용 Embedding과 LLM을 사용하므로 GPU 자원 충돌을 고려해야 합니다.

## 7. 관련 코드와 문서

- `evaluation/`
- `backend/app/services/evaluation_service.py`
- `backend/app/services/evaluation_pipeline_service.py`
- `infra/docker-compose.evaluation.yml`
- `docs/EVALUATION_GUIDE.md`
- `docs/EVALUATION_DATA_WORKFLOW.md`

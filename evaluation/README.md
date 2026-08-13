# Evaluation

RAG 기반 질의응답 시스템의 검색 및 답변 품질을 평가하기 위한 폴더

## 폴더 구조

- `evaluate_rag.py`
  - 평가셋의 `user_input`을 읽어 `/api/chat`에 자동 요청
  - 챗봇 답변과 검색 근거를 수집하여 결과 파일 생성

- `evaluate_metrics.py`
  - `evaluate_rag.py` 실행 결과를 기반으로 평가 지표 계산
  - Recall@1, Recall@3, Recall@5 및 RAGAS 지표 계산

- `datasets/`
  - 평가용 질문 및 Ground Truth 저장
  - 문서별/버전별 평가셋 관리
  - 예: `GC_FINAL_V1.xlsx`

- `source_documents/`
  - 평가에 사용한 원본 HWP/HWPX 문서 보관
  - 원본 공고가 삭제되거나 수정되어도 동일한 문서로 재현하기 위한 용도
  - 문서 ID와 버전별로 구분하여 관리
  - 예: `DOC_GC_001/v1/source.hwpx`

- `results/`
  - 평가 실행 결과 저장
  - `*_result.xlsx`: 챗봇 답변 및 검색 결과
  - `*_scored.xlsx`: Recall 및 RAGAS 평가 결과
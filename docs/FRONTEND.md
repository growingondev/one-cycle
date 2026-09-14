# Frontend

## 1. 구성

Frontend는 사용자 서비스와 관리자 서비스로 나뉩니다.

| 앱 | 위치 | 배포 주소 |
|---|---|---|
| 사용자 | `frontend/user` | https://ddokbot.codefoilo.store/ |
| 관리자 | `frontend/admin` | https://ddokbot.admin.codefoilo.store/ |

두 앱은 React 19, TypeScript, Vite 기반이며 Vercel에 배포됩니다. `/api/*` 요청은 각 `vercel.json`의 Rewrite를 통해 AWS Public API로 전달됩니다.

## 2. 사용자 서비스

- 공고 목록과 총 공고 수 표시
- 공고명 검색
- 지역·공고 상태 필터
- 최신순·오래된순 정렬
- 페이지 이동
- 공고 상세와 핵심정보 표시
- 원본 공고문 다운로드
- 선택한 공고 범위의 Chat
- 답변 근거 표시
- 청약 용어 설명

사용자 목록은 Backend가 반환하는 활성 CollectionRun의 공고만 표시합니다. 화면에 보이는 공고 수와 `page`, `size`, `total`, `total_pages`를 구분해야 합니다.

## 3. 관리자 서비스

- 관리자 로그인·로그아웃
- 전체 공고 수집
- 공고 목록·상세와 개별 재수집
- 문서 목록·상세·다운로드
- 문서 재처리와 ProcessingRun 확인
- 오류 목록·상세·상태 변경·재시도
- 용어사전 생성·수정·활성화·삭제

관리자 인증 Token은 Backend가 HttpOnly Cookie로 설정합니다. Frontend는 비밀번호 Hash나 JWT Secret을 저장하지 않습니다.

## 4. API 연결

```text
브라우저
  → 현재 Vercel 도메인의 /api/*
  → Vercel Rewrite
  → https://ddokbot-api.hwanmade.store/api/*
  → Nginx
  → FastAPI Backend
```

Frontend가 Crawler, Worker, RAG, PostgreSQL을 직접 호출하지 않습니다.

## 5. 핵심정보 표시

Backend의 `key_information` 응답에서 신청기간, 자격, 공급정보, 소득·자산, 제출서류, 당첨자 발표, 문의처를 표시합니다. 추출되지 않은 필드는 공고 전체를 숨기지 않고 해당 정보만 빈 상태로 처리합니다.

공급정보처럼 배열로 반환되는 데이터는 단지명 기준으로 묶어 표 형태로 표시할 수 있습니다. 화면 표시를 위해 Backend 원본 값을 임의로 자격 판정 결과로 바꾸지 않습니다.

## 6. 오류 처리

- 401: 관리자 로그인 화면 이동 또는 로그인 필요 안내
- 404: 공고·문서가 없거나 현재 활성 Run에 없음
- 500/502/503: 무한 Loading 대신 오류 안내
- 파일 다운로드: 응답 Header의 파일명 사용
- 상태 변경: 응답으로 받은 최신 객체로 화면 상태 갱신

## 7. 로컬 실행

```bash
cd frontend/user
npm ci
npm run dev
```

```bash
cd frontend/admin
npm ci
npm run dev
```

Production 검증:

```bash
cd frontend/user && npm ci && npm run build
cd frontend/admin && npm ci && npm run lint && npm run build
```

## 8. 핵심 파일

- `frontend/user/src/`
- `frontend/user/vercel.json`
- `frontend/admin/src/`
- `frontend/admin/vercel.json`
- `backend/app/api/routes/`

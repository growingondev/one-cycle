# 🛠️ 관리자 페이지 API 연동 가이드

 관리자 페이지 프론트엔드 UI 화면 및 상태 관리 로직 구현이 완료되어 API 연동을 위한 가이드를 전달해 드립니다.

## 📌 공통 연동 안내
* 프론트엔드 코드 내에 `// 🔓 [실제 API 연동 시 주석 해제]` 주석이 달린 부분을 검색하시면 연동 지점을 바로 찾으실 수 있습니다.
* 코드에 임시 URL (`/api/admin/...`)로 적어둔 곳에 실제 개발하신 API Endpoint를 매핑해 주시면 됩니다.

---

## 1. 📢 공고 관리
**관련 파일:** `src/pages/Announcement.tsx`, `src/pages/AnnouncementDetail.tsx`

### [GET] 공고 목록 조회
* **위치:** `Announcement.tsx` 내 `fetchNotices` 함수
* **호출 시점:** 페이지 로드 시 전체 목록 조회
* **기대 응답:** `Notice[]` 배열 리턴 요망
  * 포함되어야 할 필드: `id`, `title`, `region`, `noticeDate`, `status`, `collect` 등

### [POST] 공고 수집 수동 트리거
* **위치:** `Announcement.tsx` 내 `handleCollectRequest` 함수
* **호출 시점:** 상단 '공고 수집' 버튼 클릭 시
* **동작:** 파이프라인 트리거 API 호출

### [DELETE] 공고 삭제
* **위치:** `AnnouncementDetail.tsx` 내 `handleDelete` 함수
* **요청 형태:** `/api/admin/notices/{id}`

---

## 2. 📄 문서 관리
**관련 파일:** `src/pages/Document.tsx`

### [GET] 문서 목록 조회
* **위치:** `Document.tsx` 내 `fetchDocuments` 함수
* **호출 시점:** 페이지 로드 및 '새로고침' 버튼 클릭 시
* **기대 응답:** 파이프라인에서 처리된 문서 리스트 배열 리턴 요망
  * 포함되어야 할 필드: `id`, `targetNotice`, `docName`, `type`, `size`, `regDate`, `processStatus`, `analysisStatus`

---

## 3. ⚠️ 오류 관리
**관련 파일:** `src/pages/Error.tsx`, `src/pages/ErrorDetail.tsx`

### [GET] 오류 목록 조회
* **위치:** `Error.tsx` 내 `fetchErrors` 함수
* **기대 응답:** 파이프라인 및 시스템 오류 내역 배열 리턴 요망

### [PUT/PATCH] 오류 상태 변경
* **위치:** `ErrorDetail.tsx` 내 `handleStatusChange` 함수
* **요청 형태:** `/api/admin/errors/{id}/status`
* **요청 Body:** 새로운 상태값 전송 (예: `{ "status": "해결완료" }`)

### [POST] 처리 메모 추가
* **위치:** `ErrorDetail.tsx` 내 `handleAddNote` 함수
* **요청 형태:** `/api/admin/errors/{id}/notes`
* **요청 Body:** `{ "note": "메모내용" }`
* **기대 응답:** DB에 저장된 시간(`Date`)과 작성자(`Actor`) 정보가 포함된 완성된 메모 객체를 리턴해 주시면 프론트 UI에 즉시 반영됩니다.
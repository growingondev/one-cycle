# Frontend 개발 문서

> One Cycle 프로젝트의 Frontend 구조, 화면 구성, API 연동 방식, 주요 상태 관리 및 개발 시 참고사항을 정리한 문서입니다.
>
> 이 문서는 새로운 팀원이 프로젝트에 합류했을 때 Frontend 코드를 처음부터 하나씩 분석하지 않아도 전체 구조와 역할을 이해할 수 있도록 작성되었습니다.

---

# 1. 문서 목적

One Cycle Frontend는 크게 두 영역으로 구성되어 있습니다.

- 사용자 화면 (`user`)
- 관리자 화면 (`admin`)

사용자 화면은 LH 임대주택/청약 공고 정보를 조회하고 AI 챗봇을 통해 공고 관련 질문을 할 수 있는 서비스 화면을 담당합니다.

관리자 화면은 수집된 LH 공고와 공고에 연결된 문서, 문서 처리 상태, 오류 및 용어 사전 등을 관리하기 위한 운영자용 화면입니다.

Frontend는 React + TypeScript 기반으로 구성되어 있으며, Backend와 HTTP API를 통해 데이터를 주고받습니다.

---

# 2. 전체 Frontend 구조

현재 프로젝트의 Frontend는 다음과 같은 구조를 가지고 있습니다.

```text
frontend/
├── user/
│   └── ...
│
└── admin/
    └── src/
        ├── App.tsx
        ├── main.tsx
        │
        ├── assets/
        │   └── css/
        │
        ├── components/
        │   └── ...
        │
        └── pages/
            ├── Login.tsx
            │
            ├── Announcement.tsx
            ├── AnnouncementDetail.tsx
            │
            ├── Document.tsx
            ├── DocumentDetail.tsx
            │
            ├── Error.tsx
            ├── ErrorDetail.tsx
            │
            └── GlossaryAdmin.tsx
            3. Frontend 영역 구분
3.1 User Frontend

사용자가 직접 접속하여 사용하는 서비스 화면입니다.

주요 역할은 다음과 같습니다.

LH 공고 조회
공고 상세 확인
사용자 조건에 따른 공고 정보 확인
AI 챗봇 이용
공고 내용에 대한 질문
어려운 청약/임대주택 용어 확인
공고 및 문서 정보를 사용자에게 이해하기 쉬운 형태로 제공

User Frontend는 일반 사용자가 사용하는 서비스이므로 관리자 기능과 분리되어 있습니다.

3.2 Admin Frontend

관리자가 서비스의 데이터와 처리 상태를 관리하기 위한 화면입니다.

주요 기능은 다음과 같습니다.

관리자 로그인
공고 관리
공고 수집 요청
공고 상세 확인
개별 공고 재수집
문서 관리
문서 처리 상태 확인
문서 분석 상태 확인
문서 다운로드
문서 재처리
오류 관리
오류 상태 변경
오류 재시도
용어 사전 관리

관리자 Frontend는 Backend의 /api/admin/... API를 통해 데이터를 조회하거나 작업을 요청합니다.

4. 기술 구성

현재 Admin Frontend에서 확인되는 주요 기술은 다음과 같습니다.

기술	역할
React	UI 구성
TypeScript	타입 기반 개발
React Router	페이지 이동 및 라우팅
Fetch API	Backend API 호출
CSS	화면 스타일링
BrowserRouter	SPA 라우팅
5. Admin Frontend 진입 구조

Admin Frontend의 시작점은 main.tsx입니다.

main.tsx
    ↓
App.tsx
    ↓
React Router
    ↓
각 페이지
main.tsx

위치:

frontend/admin/src/main.tsx

주요 역할:

React 애플리케이션 시작
전역 CSS 로드
App.tsx 렌더링
StrictMode 적용

현재 구조는 다음과 같습니다.

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
6. Admin Routing

라우팅은 App.tsx에서 관리합니다.

위치:

frontend/admin/src/App.tsx

현재 주요 라우팅 구조는 다음과 같습니다.

/
└── Login

Layout
├── /announcement
│   └── Announcement
│
├── /document
│   └── Document
│
└── /error
    └── Error

코드 구조상 GlossaryAdmin도 import되어 있지만 현재 Route로 연결되어 있지는 않습니다.

즉,

import GlossaryAdmin from './pages/GlossaryAdmin';

는 존재하지만 현재 다음과 같은 Route는 없습니다.

<Route path="/glossary" element={<GlossaryAdmin />} />

따라서 현재 상태에서는 GlossaryAdmin.tsx 파일이 존재하더라도 URL을 통해 해당 페이지에 접근할 수 있도록 라우팅이 연결되어 있지 않습니다.

향후 용어 사전 관리 페이지를 실제 관리자 메뉴에 추가하려면 Route 연결이 필요합니다.

7. 관리자 인증 구조

관리자 화면의 첫 화면은 로그인 페이지입니다.

파일:

pages/Login.tsx

접속 경로:

/
7.1 로그인 처리

로그인 시 다음 API를 호출합니다.

POST /api/admin/auth/login

Request Body:

{
  "admin_id": "관리자 아이디",
  "password": "비밀번호"
}

요청 시 다음 옵션을 사용합니다.

credentials: 'include'

이는 Backend에서 사용하는 인증 쿠키/세션 정보를 브라우저 요청에 포함하기 위한 설정입니다.

7.2 로그인 성공

로그인 API가 정상적으로 처리되면 다음 페이지로 이동합니다.

/announcement

즉 관리자 로그인 후 기본 화면은 공고 관리 화면입니다.

7.3 로그인 실패

HTTP 401 응답을 받은 경우:

아이디 또는 비밀번호가 올바르지 않습니다.

메시지를 표시합니다.

그 외 오류가 발생하면:

로그인 중 오류가 발생했습니다.

를 표시합니다.

8. 관리자 API 인증 처리

관리자 페이지에서 Backend API를 호출할 때 대부분 다음과 같이 작성되어 있습니다.

fetch('/api/admin/...', {
  credentials: 'include'
})

또는 POST/PATCH 요청에서도 동일하게 사용합니다.

fetch('/api/admin/...', {
  method: 'POST',
  credentials: 'include'
})
8.1 401 처리

관리자 페이지의 대부분의 API 요청에서는 HTTP 401이 반환되었을 때 로그인 페이지로 이동합니다.

예:

if (res.status === 401) {
  navigate('/');
  return;
}

따라서 관리자 세션이 만료되거나 인증되지 않은 경우 사용자는 로그인 화면으로 이동하게 됩니다.

9. 공고 관리

공고 관리 페이지는 다음 두 파일로 구성됩니다.

pages/
├── Announcement.tsx
└── AnnouncementDetail.tsx

구조:

Announcement
    ↓
공고 목록
    ↓
공고 선택
    ↓
AnnouncementDetail
    ↓
공고 상세
10. Announcement.tsx

파일:

frontend/admin/src/pages/Announcement.tsx

역할:

수집된 LH 공고 목록을 조회하고 수집 상태를 관리하는 관리자 화면

10.1 공고 목록 API

다음 API를 사용합니다.

GET /api/admin/announcements

기본적으로 다음 Query Parameter를 사용할 수 있습니다.

page
size
search
announcement_status
collection_status

예:

/api/admin/announcements?page=1&size=10

검색어가 있는 경우:

/api/admin/announcements?page=1&size=10&search=청년

공고 상태:

announcement_status

수집 상태:

collection_status
11. 공고 목록 데이터

Frontend에서는 Backend에서 전달받은 데이터를 Notice 형태로 변환합니다.

export interface Notice {
  id: number;
  title: string;
  region: string;
  notice_type: string;
  noticeDate: string;
  status: string;
  collect: string;
  endDate?: string;
}

Backend 데이터와 화면 표시용 데이터의 이름이 일부 다르기 때문에 Mapping을 수행합니다.

예:

Backend                         Frontend
------------------------------------------------
id                              id
title                           title
region                          region
notice_type                     notice_type
announcement_date              noticeDate
announcement_status            status
collection_status              collect
application_end                endDate
12. 공고 수집 상태

공고 수집 상태는 다음 값을 사용합니다.

running
success
partial
failed

화면 표시:

API 값	화면 표시
running	수집중
success	수집완료
partial	부분완료
failed	수집실패
13. 공고 상태 Badge

공고 상태에 따라 Badge 스타일을 적용합니다.

success / 완료 / 공고중
    → green

running / partial / 수집중
    → orange

failed / 실패 / 오류
    → red

그 외
    → gray

이 로직은 getBadgeClass()에서 처리합니다.

14. 공고 검색 및 필터

공고 관리 화면에서는 다음 기능을 제공합니다.

공고명 검색
공고명 검색

Backend Query:

search
공고 상태
공고 상태

Backend Query:

announcement_status
수집 상태
수집 상태 전체
수집중
수집완료
부분완료
수집실패

Backend Query:

collection_status
15. 공고 수집 요청

공고 목록 화면의

＋ 공고 수집

버튼을 누르면 다음 API를 호출합니다.

POST /api/admin/announcements/collect

정상 요청 시:

공고 수집 작업을 요청했습니다.

메시지를 표시합니다.

이 기능은 Frontend가 직접 크롤링하는 것이 아니라 Backend에 공고 수집 작업을 요청하는 구조입니다.

16. 공고 상세

파일:

pages/AnnouncementDetail.tsx

공고 목록에서 공고를 선택하면 상세 화면이 표시됩니다.

상세 조회 API:

GET /api/admin/announcements/{id}

예:

GET /api/admin/announcements/123
17. 공고 상세에서 표시하는 정보

현재 주요 정보 영역에는 다음 항목이 표시됩니다.

공고 상태
수집 상태
접수 기간
신청 자격
제출 서류
문의처
연결된 문서 수

또한 기본 공고 정보로:

공고명
지역
공고유형
식별 ID

를 표시합니다.

18. 공고 원본 링크

Backend에서 detail_url이 전달되는 경우:

🔗 원본 공고 바로가기

링크를 표시합니다.

해당 링크는 새 브라우저 탭에서 열립니다.

중요한 점은 Frontend가 임의로 공고 URL을 생성하지 않는다는 것입니다.

{detail.detail_url && (
  <a href={detail.detail_url} ...>

즉 Backend가 전달한 detail_url을 그대로 사용합니다.

19. 공고 개별 재수집

공고 상세 화면에서:

↻ 개별 재수집

버튼을 사용할 수 있습니다.

API:

POST /api/admin/announcements/{id}/recollect

정상 요청 시:

재수집 요청이 완료되었습니다.

를 표시합니다.

20. 주요 정보 JSON 표시

공고 상세의 일부 데이터는 단순 문자열이 아니라 객체 또는 배열 형태일 수 있습니다.

예:

key_information
├── application_period
├── eligibility
├── required_documents
└── contact_information

이 데이터를 그대로 React에서 출력하면 객체가 [object Object] 형태로 표시될 수 있습니다.

이를 방지하기 위해 formatKeyInfo() 함수가 사용됩니다.

지원하는 형태:

null
undefined
문자열
숫자
boolean
배열
객체

배열은 목록 형태로 표시하고 객체는 key/value 구조로 재귀적으로 표시합니다.

21. 문서 관리

문서 관리는 다음 두 파일로 구성됩니다.

pages/
├── Document.tsx
└── DocumentDetail.tsx

구조:

Document
    ↓
문서 목록
    ↓
문서 선택
    ↓
DocumentDetail
    ↓
문서 상세
22. Document.tsx

파일:

frontend/admin/src/pages/Document.tsx

역할:

공고에 연결된 HWP/HWPX 등의 문서 처리 및 AI 분석 상태를 확인하는 관리자 화면

23. 문서 목록 API

API:

GET /api/admin/documents

Query Parameter:

page
size
search
document_type
processing_status
analysis_status

예:

/api/admin/documents?page=1&size=10

문서 유형 필터:

document_type

처리 상태:

processing_status

분석 상태:

analysis_status
24. 문서 데이터 구조

Frontend에서 사용하는 인터페이스:

export interface DocumentItem {
  id: number;
  targetNotice: string;
  docName: string;
  type: string;
  size: string;
  regDate: string;
  processStatus: string;
  analysisStatus: string;
  downloadStatus: string;
}

Backend 응답을 화면 표시용 데이터로 변환합니다.

주요 Mapping:

Backend                         Frontend
------------------------------------------------
id                              id
announcement_title             targetNotice
document_name / file_name      docName
document_type                  type
file_size                      size
created_at                     regDate
processing_status              processStatus
analysis_status                analysisStatus
download_status                downloadStatus
25. 문서 처리 상태

처리 상태는 다음 값을 사용합니다.

pending
running
succeeded
failed

화면 표시:

API 값	화면 표시
pending	대기
running	처리중
succeeded	처리완료
failed	처리실패
26. 문서 분석 상태

분석 상태:

not_run
pending
pass
warning
fail

화면 표시:

API 값	화면 표시
not_run	미실행
pending	대기
pass	검증통과
warning	경고
fail	검증실패
27. 문서 통계

문서 관리 화면 상단에는 다음 통계를 표시합니다.

전체 문서
처리 완료
처리 중
처리 실패

현재 통계는 별도의 통계 API가 아니라 동일한 문서 목록 API를 상태별로 호출하여 계산합니다.

예를 들어 전체 문서 수:

GET /api/admin/documents?page=1&size=1

처리 완료:

GET /api/admin/documents?page=1&size=1&processing_status=succeeded

처리 중:

GET /api/admin/documents?page=1&size=1&processing_status=running

처리 실패:

GET /api/admin/documents?page=1&size=1&processing_status=failed

네 요청을 Promise.all()로 동시에 호출합니다.

28. 파일 크기 표시

Backend에서 file_size가 byte 단위 숫자로 전달되는 경우 formatFileSize()를 이용해 사람이 읽기 쉬운 형태로 변환합니다.

예:

1024
→ 1.0 KB

1024 * 1024
→ 1.0 MB

지원 단위:

B
KB
MB
29. 문서 다운로드

문서 목록에서 다운로드 가능한 문서는:

다운로드

버튼을 제공합니다.

API:

GET /api/admin/documents/{id}/download

응답으로 파일 Blob을 받은 뒤 Browser의 Object URL을 생성하여 다운로드합니다.

구조:

Frontend
    ↓
GET /api/admin/documents/{id}/download
    ↓
Backend
    ↓
파일 응답
    ↓
Blob
    ↓
Browser 다운로드
30. 문서 다운로드 예외

다음 상태를 별도로 처리합니다.

401
→ 로그인 페이지 이동

404
→ 해당 문서가 없음

409
→ 다운로드 가능한 파일 없음
31. 문서 상세

파일:

pages/DocumentDetail.tsx

API:

GET /api/admin/documents/{id}

문서 상세에서는 문서 처리 파이프라인과 관련된 정보를 확인할 수 있습니다.

32. 문서 상세 표시 정보

현재 다음 정보를 표시합니다.

파일명
저장 경로
체크섬
처리 단계
오류 메시지
청킹 완료 수
임베딩 완료 수

특히 다음 영역은 문서 처리 Pipeline과 연결되는 개념입니다.

문서 처리
    ↓
구조화
    ↓
청킹
    ↓
임베딩

현재 관리자 화면에서는 청킹 및 임베딩 완료 수를 확인할 수 있도록 구성되어 있습니다.

33. 문서 재처리

문서 상세에서:

↻ 문서 재처리

버튼을 제공합니다.

API:

POST /api/admin/documents/{id}/reprocess

409 응답이 발생하면:

현재 상태에서는 재처리할 수 없습니다.

를 표시합니다.

34. 오류 관리

오류 관리는 다음 두 파일로 구성됩니다.

pages/
├── Error.tsx
└── ErrorDetail.tsx

구조:

Error
    ↓
오류 목록
    ↓
오류 선택
    ↓
ErrorDetail
    ↓
오류 상세 및 상태 관리
35. Error.tsx

파일:

pages/Error.tsx

역할:

공고 수집, 문서 처리, 분석 및 기타 Backend Pipeline 과정에서 발생한 오류를 관리자에게 보여주고 관리하기 위한 화면

36. 오류 목록 API

API:

GET /api/admin/errors

Query Parameter:

page
size
search
error_type
status
37. 오류 유형

현재 Frontend에서 정의된 오류 유형:

collection
download
parsing
normalizing
structuring
verification
chunking
embedding
database
rag
llm

화면 표시:

API 값	화면 표시
collection	공고 수집
download	파일 다운로드
parsing	문서 파싱
normalizing	정규화
structuring	구조화
verification	검증
chunking	청킹
embedding	임베딩
database	데이터베이스
rag	RAG
llm	LLM
38. 오류 상태

현재 오류 상태:

unresolved
in_progress
resolved

화면 표시:

API 값	화면 표시
unresolved	미해결
in_progress	해결중
resolved	해결완료
39. 오류 통계

오류 관리 화면 상단에는 다음 통계를 표시합니다.

전체 오류
미해결
해결 중
해결 완료

통계 역시 현재는 별도의 통계 API가 아니라 오류 목록 API를 상태별로 호출하여 계산합니다.

40. 오류 목록 데이터 Mapping

Backend 응답은 다음과 같이 화면용 데이터로 변환합니다.

Backend                         Frontend
------------------------------------------------
id                              id
created_at                      time
error_type                      type
stage                           stage
announcement_title             target
document_name                   target
message                         message
status                          status

공고명과 문서명이 모두 존재하면:

공고명 / 문서명

형태로 표시합니다.

41. 오류 상세

파일:

pages/ErrorDetail.tsx

API:

GET /api/admin/errors/{id}

상세 화면에서는 오류의 현재 상태와 발생 정보를 확인할 수 있습니다.

42. 오류 상세 정보

현재 다음 정보를 표시합니다.

오류 코드
발생 시각
해결 시각
발생 단계
대상 공고
대상 문서
입력된 해결 내용

그리고 오류 메시지를 별도로 표시합니다.

43. 오류 상태 변경

관리자는 오류 상세 화면에서 상태를 변경할 수 있습니다.

가능한 상태:

미해결
해결중
해결완료

API:

PATCH /api/admin/errors/{id}/status

Request Body:

{
  "status": "resolved",
  "resolution": "해결 내용"
}

resolution은 선택적으로 입력할 수 있습니다.

44. 오류 재시도

오류 상세 화면에는:

↻ 재시도

버튼이 있습니다.

API:

POST /api/admin/errors/{id}/retry

409 응답:

현재 재시도 할 수 없는 상태입니다.
45. 용어 사전 관리

파일:

pages/GlossaryAdmin.tsx

역할:

사용자 챗봇 화면에서 어려운 청약/임대주택 용어를 툴팁으로 설명하기 위한 용어 사전 관리 화면

46. 현재 용어 사전 구현 상태

중요:

현재 GlossaryAdmin.tsx는 Backend API와 연동된 상태가 아닙니다.

초기 데이터:

const initialDummyData = [...]

를 사용하며 React State로 데이터를 관리합니다.

따라서 현재 상태에서:

용어 추가
용어 수정
용어 삭제
ON/OFF 변경

등을 수행해도 실제 Backend DB에 저장되는 구조가 아닙니다.

페이지 새로고침 또는 애플리케이션 재시작 시 실제 DB 데이터가 유지되는 구조가 아닙니다.

향후 실제 서비스에 적용하려면 Backend API 연동이 필요합니다.

47. 용어 사전 데이터 구조
export interface GlossaryItem {
  id: number;
  term: string;
  definition: string;
  category: string;
  is_active: boolean;
}

각 필드의 의미:

필드	의미
id	용어 식별 ID
term	용어
definition	용어 설명
category	용어 카테고리
is_active	사용자 화면 노출 여부
48. 용어 사전 카테고리

현재 UI에서 사용되는 카테고리:

청약/자격
소득/자산
주택/면적
주택/유형
청약/당첨
비용/계약
49. 용어 사전 검색

현재 다음 기준으로 검색할 수 있습니다.

용어
설명

검색은 현재 Frontend의 filter()를 사용해 처리합니다.

Backend 검색 API를 사용하는 방식이 아닙니다.

50. 용어 활성화 상태

is_active가 true인 용어는:

ON

false인 용어는:

OFF

로 표시됩니다.

UI 설명상 활성화된 용어는 사용자 화면 챗봇 툴팁에 노출되는 용도로 설계되어 있습니다.

다만 현재 GlossaryAdmin.tsx 자체는 Backend와 연동되어 있지 않기 때문에 실제 사용자 화면과의 데이터 연동은 별도로 구현되어야 합니다.

51. 용어 추가/수정

용어 추가 및 수정은 Modal을 이용합니다.

입력 항목:

카테고리
용어
용어 설명
활성화 여부

필수 입력:

용어
용어 설명
52. 용어 삭제

삭제 버튼을 누르면 Browser의 confirm()을 이용해 삭제 여부를 확인합니다.

정말로 이 용어를 삭제하시겠습니까?

확인하면 현재 React State에서 해당 데이터를 제거합니다.

53. 용어 Toast

용어 추가/수정/삭제/상태 변경 등의 작업이 완료되면 Toast 메시지를 표시합니다.

예:

새로운 용어가 추가되었습니다.
용어가 성공적으로 수정되었습니다.
용어가 삭제되었습니다.
상태가 ON으로 변경되었습니다.
54. 현재 관리자 화면 구현 상태 요약

현재 확인된 구현 상태는 다음과 같습니다.

기능	Frontend	Backend API 연동
관리자 로그인	O	O
공고 목록	O	O
공고 검색	O	O
공고 상태 필터	O	O
수집 상태 필터	O	O
전체 공고 수집	O	O
공고 상세	O	O
공고 개별 재수집	O	O
문서 목록	O	O
문서 검색	O	O
문서 유형 필터	O	O
문서 처리 상태 필터	O	O
문서 분석 상태 필터	O	O
문서 통계	O	O
문서 상세	O	O
문서 다운로드	O	O
문서 재처리	O	O
오류 목록	O	O
오류 검색	O	O
오류 유형 필터	O	O
오류 상태 필터	O	O
오류 통계	O	O
오류 상세	O	O
오류 상태 변경	O	O
오류 재시도	O	O
용어 사전 UI	O	X
용어 사전 CRUD	O	X
용어 사전 Route	X	-
55. API 구조

관리자 API는 /api/admin을 기준으로 구성되어 있습니다.

전체 구조:

/api/admin
│
├── /auth
│   └── /login
│
├── /announcements
│   ├── GET /
│   ├── POST /collect
│   ├── GET /{id}
│   └── POST /{id}/recollect
│
├── /documents
│   ├── GET /
│   ├── GET /{id}
│   ├── GET /{id}/download
│   └── POST /{id}/reprocess
│
└── /errors
    ├── GET /
    ├── GET /{id}
    ├── PATCH /{id}/status
    └── POST /{id}/retry

위 API 목록은 현재 Frontend 코드에서 실제 호출하고 있는 Endpoint를 기준으로 정리한 것입니다.
Backend에 존재하지만 현재 Frontend 코드에서 사용하지 않는 API는 이 문서에서 별도로 정의하지 않습니다.

56. 페이지네이션

공고, 문서, 오류 목록은 페이지네이션을 사용합니다.

기본적으로:

page = 현재 페이지
size = 10

을 사용합니다.

Backend 응답에서:

items
total
total_pages

값을 받아 화면에 표시합니다.

예:

{
  "items": [],
  "total": 100,
  "total_pages": 10
}
57. 검색 동작

검색은 대부분 다음 패턴으로 구현되어 있습니다.

사용자가 검색어 입력
        ↓
검색 버튼 클릭
        ↓
현재 page가 1이면 API 직접 호출
        ↓
현재 page가 1이 아니면 page를 1로 변경
        ↓
useEffect를 통해 API 호출

Enter 키를 눌러 검색할 수 있는 화면도 있습니다.

58. 상세 페이지 처리 방식

현재 공고/문서/오류 화면은 별도의 URL Route로 이동하지 않고 부모 컴포넌트 내부에서 선택 상태를 이용해 상세 컴포넌트를 표시합니다.

예:

const [selectedNoticeId, setSelectedNoticeId] =
  useState<number | null>(null);

값이 존재하면:

if (selectedNoticeId) {
  return (
    <AnnouncementDetail
      id={selectedNoticeId}
      onBack={...}
    />
  );
}

즉 현재 구조는:

/announcement
    ↓
Announcement
    ↓
selectedNoticeId 설정
    ↓
AnnouncementDetail 표시

방식입니다.

문서와 오류도 같은 구조입니다.

59. 목록으로 돌아가기

상세 화면에서는:

← 목록으로

버튼을 제공합니다.

버튼 클릭 시:

selected ID = null

로 변경하여 목록 화면을 다시 표시합니다.

필요한 경우 목록 데이터를 다시 조회합니다.

60. 로딩 처리

API 요청 중에는 로딩 상태를 관리합니다.

예:

const [isLoading, setIsLoading] = useState(false);

목록 조회 중에는:

불러오는 중...

또는:

데이터를 불러오는 중입니다...

등을 표시합니다.

61. API 오류 처리 기본 원칙

현재 Frontend에서 공통적으로 다음 HTTP 상태를 중요하게 처리합니다.

401
인증되지 않음

처리:

로그인 페이지로 이동
404
대상 데이터가 없음

처리:

알림 표시
목록으로 이동
409
현재 상태에서는 요청할 수 없음

문서 재처리, 오류 재시도, 문서 다운로드 등의 상황에서 사용됩니다.

그 외 오류

일반적인 서버 오류 메시지를 Alert로 표시합니다.

62. Backend와 Frontend의 역할 분리

이 프로젝트에서 중요한 원칙은 Frontend가 실제 데이터 처리 Pipeline을 수행하지 않는다는 것입니다.

예를 들어 공고 수집의 경우:

Frontend
    ↓
수집 요청 API
    ↓
Backend
    ↓
Crawler
    ↓
공고 파일 수집
    ↓
문서 처리
    ↓
구조화
    ↓
청킹
    ↓
임베딩
    ↓
Database

Frontend의 역할은:

관리자에게 현재 상태를 보여주고
관리자의 작업 요청을 Backend에 전달하는 것

입니다.

63. 공고 처리 구조 이해하기

공고 관리 화면에서 관리하는 데이터와 문서 관리 화면에서 관리하는 데이터는 서로 연결되어 있습니다.

개념적으로:

공고
│
├── 공고 기본 정보
│
└── 연결된 문서
      │
      ├── HWP
      ├── HWPX
      └── 기타 문서

문서는 이후 Backend Pipeline에서 처리될 수 있습니다.

원본 문서
    ↓
파싱
    ↓
정규화
    ↓
구조화
    ↓
검증
    ↓
청킹
    ↓
임베딩

오류 관리 화면에서는 이 과정에서 발생한 오류를 관리합니다.

64. 오류 단계와 Pipeline

현재 오류 유형에는 다음 단계들이 정의되어 있습니다.

collection
download
parsing
normalizing
structuring
verification
chunking
embedding
database
rag
llm

따라서 관리자 오류 화면을 통해 단순한 Frontend 오류뿐 아니라 공고 수집부터 AI/RAG 처리 단계까지 발생한 오류를 관리할 수 있도록 설계되어 있습니다.

65. Frontend에서 임의로 URL을 생성하지 않는 데이터

공고 원본 URL과 같이 Backend에서 관리해야 하는 값은 Frontend가 임의로 조합하지 않습니다.

대표적으로:

detail_url

은 Backend 응답에서 전달받은 값을 사용합니다.

따라서 Backend API 계약이 변경되어 URL 필드 이름이나 구조가 변경되는 경우 Frontend Mapping 코드도 함께 확인해야 합니다.

66. 새로운 팀원이 코드를 수정할 때 확인할 것

새로운 기능을 추가하거나 기존 화면을 수정할 때 다음 순서로 확인하는 것을 권장합니다.

1. 어떤 화면인가?
        ↓
2. 해당 화면의 page 파일은 무엇인가?
        ↓
3. 어떤 Backend API를 사용하는가?
        ↓
4. Request Parameter는 무엇인가?
        ↓
5. Backend Response 구조는 무엇인가?
        ↓
6. Frontend에서 어떤 Mapping을 하는가?
        ↓
7. Loading / Error / 401 / 404 / 409 처리가 필요한가?
        ↓
8. 상세 화면과 목록 화면의 데이터 갱신이 필요한가?
67. API를 수정할 때 주의할 점

Backend API의 필드 이름이 변경되면 Frontend Mapping 코드를 함께 수정해야 합니다.

예를 들어 현재:

announcement_status

를 사용하고 있는데 Backend에서:

status

로 변경된다면 Frontend도 수정해야 합니다.

현재 코드에서는 다음과 같이 Backend 필드를 직접 참조하는 부분이 많습니다.

item.announcement_status
item.collection_status
item.processing_status
item.analysis_status
item.document_name
item.created_at

따라서 API Response 구조를 변경할 경우 Frontend를 함께 확인해야 합니다.

68. any 타입 사용 부분

현재 관리자 화면에서는 일부 API Response에 대해:

const [detail, setDetail] = useState<any>(null);

형태를 사용하고 있습니다.

또한 Mapping 과정에서:

.map((item: any) => ...)

형태도 사용합니다.

이는 현재 개발 단계에서 Backend Response 구조를 유연하게 처리하기 위한 방식입니다.

향후 유지보수성을 높이려면 API Response에 대응하는 TypeScript interface/type을 정의하는 것이 좋습니다.

예:

interface AnnouncementDetailResponse {
  id: number;
  title: string;
  region: string;
  notice_type: string;
  ...
}
69. 현재 코드에서 개선할 수 있는 부분

현재 구현된 기능을 유지하면서 향후 개선할 수 있는 부분은 다음과 같습니다.

69.1 API 타입 정의

현재 일부 API Response가 any입니다.

향후:

AnnouncementResponse
DocumentResponse
ErrorResponse
...

등의 타입을 정의하면 API 변경 시 TypeScript에서 오류를 빠르게 발견할 수 있습니다.

69.2 API 호출 공통화

현재 각 컴포넌트에서 직접:

fetch(...)

를 호출합니다.

향후 다음과 같은 API Layer를 만들 수 있습니다.

src/
├── api/
│   ├── auth.ts
│   ├── announcements.ts
│   ├── documents.ts
│   └── errors.ts

그러면 UI 컴포넌트와 API 통신 로직을 분리할 수 있습니다.

69.3 인증 처리 공통화

현재 각 API 요청에서:

if (res.status === 401) {
  navigate('/');
}

를 반복하고 있습니다.

향후 공통 API Client를 만들면 401 처리 로직을 중앙화할 수 있습니다.

69.4 Toast/Alert 공통화

현재 오류 및 작업 결과를 주로:

alert(...)

로 표시합니다.

향후 공통 Toast 컴포넌트를 만들면 관리자 화면 전체의 UX를 통일할 수 있습니다.

70. 용어 사전 API 연동 시 고려사항

GlossaryAdmin.tsx는 현재 더미 데이터 기반이므로 Backend 연동 시 다음 API가 필요할 수 있습니다.

예시 구조:

GET
/api/admin/glossary

POST
/api/admin/glossary

PATCH
/api/admin/glossary/{id}

DELETE
/api/admin/glossary/{id}

단, 위 API는 현재 Frontend 코드에서 실제 사용하고 있는 API가 아닙니다.

향후 Backend API를 설계할 때 고려할 수 있는 예시이며, 실제 API 계약이 확정되면 그 계약을 기준으로 Frontend를 수정해야 합니다.

71. 용어 사전과 사용자 챗봇의 관계

서비스 설계상 용어 사전은 사용자 화면의 챗봇에서 어려운 청약 용어를 설명하기 위한 목적으로 만들어졌습니다.

개념적으로:

관리자
    ↓
용어 사전 등록/수정
    ↓
Backend Database
    ↓
사용자 Frontend
    ↓
챗봇 답변/용어 Tooltip

현재 GlossaryAdmin.tsx는 이 구조 중 관리자 UI 부분만 구현되어 있고 Backend Database와의 연결은 아직 구현되지 않은 상태입니다.

72. 개발 시 화면별 담당 파일 빠르게 찾기
작업	파일
관리자 로그인	pages/Login.tsx
공고 목록	pages/Announcement.tsx
공고 상세	pages/AnnouncementDetail.tsx
문서 목록	pages/Document.tsx
문서 상세	pages/DocumentDetail.tsx
오류 목록	pages/Error.tsx
오류 상세	pages/ErrorDetail.tsx
용어 사전	pages/GlossaryAdmin.tsx
관리자 Route	App.tsx
React 시작점	main.tsx
공통 CSS	assets/css/common.css
Layout CSS	assets/css/layout.css
로그인 CSS	assets/css/login.css
73. 기능 수정 시 추천 작업 순서

예를 들어 공고 목록에 새로운 필터를 추가한다고 가정합니다.

Step 1. UI 추가

Announcement.tsx

<select>
  ...
</select>
Step 2. State 추가
const [newFilter, setNewFilter] = useState('');
Step 3. API Query 추가
...(newFilter && {
  new_filter: newFilter
}),
Step 4. Backend API 계약 확인

Backend가 실제로:

new_filter

를 Query Parameter로 지원하는지 확인합니다.

Step 5. 결과 확인

API 응답에 변경이 있다면 Mapping도 확인합니다.

74. 상세 페이지 수정 시 주의사항

현재 상세 페이지는 다음과 같은 Props 구조를 사용합니다.

interface AnnouncementDetailProps {
  id: number;
  onBack: () => void;
}

문서:

interface DocumentDetailProps {
  id: number;
  onBack: () => void;
}

오류:

interface ErrorDetailProps {
  id: number;
  onBack: () => void;
}

따라서 상세 페이지 자체에서 목록 상태를 직접 관리하기보다는 부모 목록 컴포넌트가:

선택 ID
목록 복귀
목록 재조회

를 담당하는 구조입니다.

75. 데이터 흐름 요약

관리자 공고 화면을 예로 들면:

관리자 브라우저
      │
      │ GET /api/admin/announcements
      ↓
Backend
      │
      │ JSON
      ↓
Announcement.tsx
      │
      │ Mapping
      ↓
Notice[]
      │
      ↓
HTML Table

공고 수집 요청은 반대로:

관리자
  │
  │ "공고 수집" 클릭
  ↓
Announcement.tsx
  │
  │ POST /api/admin/announcements/collect
  ↓
Backend
  │
  │ 수집 작업 처리
  ↓
Crawler / Pipeline
76. 관리자 Frontend 전체 구조 요약
                    Admin Frontend
                           │
             ┌─────────────┴─────────────┐
             │                           │
          Login                       Layout
             │                           │
             │            ┌──────────────┼──────────────┐
             │            │              │              │
             ↓            ↓              ↓              ↓
       인증 처리       공고 관리       문서 관리       오류 관리
                          │              │              │
                    ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
                    │           │  │           │  │           │
                   목록        상세 목록       상세 목록       상세
                    │           │  │           │  │           │
                    ↓           ↓  ↓           ↓  ↓           ↓
                  API         API API         API API         API
                    │           │  │           │  │           │
                    └───────────┴──┴───────────┴──┴───────────┘
                                      │
                                      ↓
                                   Backend
77. 현재 프로젝트를 이해하기 위한 핵심 개념

이 프로젝트의 Frontend를 처음 보는 경우 다음 세 가지를 먼저 이해하면 됩니다.

1. Frontend는 화면과 사용자 작업을 담당
조회
검색
필터
버튼
상태 표시
다운로드

등을 담당합니다.

2. Backend는 실제 데이터와 처리 작업을 담당
DB
Crawler
문서 처리
구조화
청킹
임베딩
RAG
LLM

등의 실제 처리는 Backend 측에서 담당합니다.

3. Frontend와 Backend 사이의 연결은 API

예:

GET /api/admin/documents

Frontend:

"문서 목록을 주세요."

Backend:

문서 목록 JSON 응답

Frontend:

테이블에 표시

라는 흐름입니다.

78. 신규 팀원 온보딩 권장 순서

처음 프로젝트에 합류한 팀원이라면 다음 순서로 코드를 확인하는 것을 권장합니다.

1단계
frontend/admin/src/main.tsx

React 애플리케이션 시작 구조를 확인합니다.

2단계
frontend/admin/src/App.tsx

페이지 Routing 구조를 확인합니다.

3단계
pages/Login.tsx

관리자 인증 방식을 확인합니다.

4단계
pages/Announcement.tsx
pages/AnnouncementDetail.tsx

목록 → 상세 구조와 API 호출 방식을 이해합니다.

5단계
pages/Document.tsx
pages/DocumentDetail.tsx

문서 처리 Pipeline과 관리자 화면이 어떻게 연결되는지 확인합니다.

6단계
pages/Error.tsx
pages/ErrorDetail.tsx

Backend Pipeline에서 발생한 오류를 Frontend에서 어떻게 관리하는지 확인합니다.

7단계
pages/GlossaryAdmin.tsx

현재 더미 데이터 기반으로 구현되어 있는 용어 사전 UI와 향후 API 연동이 필요한 부분을 확인합니다.

79. 현재 구현과 향후 개발을 구분해서 보기

코드를 볼 때 다음을 구분해야 합니다.

[현재 구현됨 + Backend 연동]
- 관리자 로그인
- 공고 관리
- 공고 수집
- 공고 재수집
- 문서 관리
- 문서 다운로드
- 문서 재처리
- 오류 관리
- 오류 상태 변경
- 오류 재시도

[UI 구현됨 + Backend 미연동]
- 용어 사전

[현재 Route 미연결]
- GlossaryAdmin

따라서 GlossaryAdmin.tsx 파일이 존재한다고 해서 용어 사전 기능이 전체적으로 완성된 것으로 판단하면 안 됩니다.

80. 개발 문서 유지 방법

Frontend 기능을 추가하거나 API 계약이 변경되면 이 문서도 함께 수정해야 합니다.

특히 다음 내용이 변경될 경우 FRONTEND.md를 업데이트합니다.

페이지 추가
Route 추가/변경
API Endpoint 변경
API Request Parameter 변경
API Response 구조 변경
상태값 변경
신규 필터 추가
관리자 기능 추가
사용자 화면 기능 추가
기존 기능의 Backend 연동 여부 변경
81. API 변경 시 체크리스트

Backend API를 변경했다면 Frontend에서 다음을 확인합니다.

□ Endpoint URL
□ HTTP Method
□ Query Parameter
□ Request Body
□ Response JSON 구조
□ HTTP Status Code
□ 401 처리
□ 404 처리
□ 409 처리
□ Loading 처리
□ Error 처리
□ TypeScript 타입
□ 화면 Mapping
82. 신규 페이지 추가 체크리스트

새로운 관리자 페이지를 추가할 경우:

□ pages/에 컴포넌트 생성
□ App.tsx에 Route 추가
□ 필요한 API 정의/연동
□ Loading 상태 처리
□ API 오류 처리
□ 401 처리
□ 검색/필터가 필요한 경우 Query 처리
□ 페이지네이션이 필요한 경우 page/size 처리
□ 상세 화면이 필요한 경우 목록 ↔ 상세 이동 처리
□ 관리자 Layout과 스타일 확인
□ FRONTEND.md 업데이트
83. 마무리

One Cycle의 Frontend는 크게 사용자 서비스와 관리자 운영 시스템으로 나뉩니다.

관리자 Frontend는 단순한 데이터 조회 화면이 아니라 다음 Backend Pipeline을 운영자가 확인하고 제어할 수 있도록 구성되어 있습니다.

LH 공고
   ↓
공고 수집
   ↓
문서 다운로드
   ↓
문서 파싱
   ↓
정규화
   ↓
구조화
   ↓
검증
   ↓
청킹
   ↓
임베딩
   ↓
Database
   ↓
RAG
   ↓
LLM
   ↓
사용자 서비스

관리자 화면에서는 이 Pipeline과 관련하여:

공고
문서
오류

를 중심으로 상태를 확인하고 필요한 작업을 요청할 수 있습니다.

현재 Frontend에서 Backend와 실제로 연동되어 있는 주요 기능은:

관리자 로그인
공고 관리
공고 수집
공고 재수집
문서 관리
문서 다운로드
문서 재처리
오류 관리
오류 상태 변경
오류 재시도

이며,

용어 사전 관리

는 현재 UI가 구현되어 있지만 Backend API 연동 및 Route 연결이 아직 완료되지 않은 상태입니다.

새로운 팀원이 Frontend를 수정할 때는 화면 코드만 수정하기보다는 해당 화면이 호출하는 Backend API의 Request/Response 구조까지 함께 확인하는 것을 권장합니다.

특히 이 프로젝트에서는 공고 → 문서 → 처리 Pipeline → 오류 관리가 서로 연결되어 있으므로, 하나의 화면만 독립적으로 이해하기보다는 전체 데이터 흐름을 함께 이해하는 것이 중요합니다.


### 이번에 기존 문서에서 특히 바로잡아야 하는 부분

이번에 네가 보내준 `admin/src` 코드를 기준으로 보면 **이 3가지는 기존 문서에 반드시 명확하게 적어두는 게 좋아.**

1. **`GlossaryAdmin.tsx`는 아직 DB/API 연동이 안 됨**
   - 현재 `initialDummyData` 사용
   - CRUD도 React State에서만 동작
   - 새로고침하면 데이터 유지 안 됨

2. **`GlossaryAdmin`은 `App.tsx`에서 Route가 연결되지 않음**
   - 파일은 존재
   - `import`도 되어 있음
   - 하지만 실제 `<Route>`가 없음

3. **공고/문서/오류 상세는 별도 URL Route가 아니라 부모 페이지의 `selectedId` State로 전환**
   - 예: `/announcement/123` 방식이 아님
   - `Announcement → selectedNoticeId → AnnouncementDetail` 구조
   - 문서와 오류도 동일한 패턴

이 세 가지를 명시해 놓으면 **나중에 새로 들어온 팀원이 “파일은 있는데 왜 페이지가 안 나오지?”, “용어를 추가했는데 왜 페이지가 안 나오지?”, “상세 페이지 URL이 왜 안 바뀌지?” 같은 혼란을 크게 줄일 수 있어.**
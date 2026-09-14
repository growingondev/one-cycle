# Frontend 개발 문서

이 문서는 프로젝트의 Frontend 담당자가 구현한 기능과 화면 구조,
Backend와의 연결 방식, 데이터 흐름, 현재 구현 상태 및 향후 분리 시
고려사항을 정리한 문서입니다.

이 문서의 목적은 특정 개발자만 프로젝트를 이해할 수 있는 상태를
방지하고, 새로운 팀원이 프로젝트에 합류했을 때 "이 화면이 왜 존재하고,
어떤 데이터를 받아서, 어떤 방식으로 화면에 표시하는지"를 빠르게 이해할
수 있도록 하는 것입니다.

> **최종 확인 기준:** 2026-09-14 `develop-api` (`2b2b564`)
>
> 2026-08-28 최초 작성 내용의 개념과 책임 구분은 유지하고, 이후 실제로
> 구현된 화면 고도화, Docker 서비스 분리, Vercel 배포, HTTPS 및 CI/CD
> 변경사항만 갱신했다.

## 1. 담당 파트 개요

### 1.1 Frontend의 역할

이 프로젝트의 Frontend는 사용자가 공공임대주택 및 청약 관련 정보를 쉽고
직관적으로 확인할 수 있도록 사용자 화면과 관리자 화면을 제공하는 역할을
담당한다.

Frontend에서 담당하는 주요 영역은 다음과 같다.

-   공고 목록 화면
-   공고 상세 화면
-   AI 챗봇 화면
-   챗봇 답변 및 근거 정보 표시
-   핵심 정보 요약 카드 표시
-   청약 용어 사전 화면
-   관리자 용어 사전 관리 화면
-   Backend API와의 데이터 통신
-   사용자 입력 및 화면 상태 관리
-   API 응답 데이터의 화면 표시
-   로딩 / 오류 / 검색 결과 없음 등의 UI 상태 처리
-   반응형 UI 및 화면 레이아웃 관리

Frontend는 문서 원본을 직접 파싱하거나 AI 답변을 생성하지 않는다.

전체적으로 다음과 같은 역할 분리를 전제로 한다.

``` text
Frontend
    │
    │ HTTP API
    ▼
Backend
    │
    ├── 공고 데이터
    ├── 핵심정보
    ├── 챗봇/RAG
    ├── 용어사전
    └── 기타 데이터 처리
```

즉 Frontend의 기본 책임은 Backend가 제공하는 데이터를 사용자에게
이해하기 쉬운 형태로 표현하는 것이다.

## 2. 프로젝트에서 Frontend가 담당하는 기능

### 2.1 사용자 서비스

현재 사용자 서비스에서 Frontend가 담당하는 주요 기능은 다음과 같다.

**공고 목록**

사용자가 등록된 공공주택/청약 공고를 목록 형태로 확인할 수 있다.

**주요 표시 정보 예:**

-   공고명
-   공고 유형
-   지역
-   신청기간
-   마감일
-   기타 공고 메타데이터

**누적 주요 수정 사항:**

-   공고 목록 데이터가 한 칸씩 밀리는 현상 수정
-   공고 마감일의 `T10:00`과 같은 ISO datetime 문자열이 사용자 화면에
    그대로 표시되지 않도록 수정
-   공고 제목의 불필요한 공백을 정리하고 지역명을 화면 폭에 맞게 표시
-   데스크톱 표와 모바일 카드 레이아웃을 구분하고 공통 페이지네이션 적용
-   공고문 원본 파일 다운로드 기능 추가
-   상세 화면에 공급정보와 신청자격의 펼침 영역 추가
-   AI 답변의 근거 문단을 접이식 목록과 전체 내용 보기로 개선

**관련 작업 커밋:**

-   `f33632a`
    -   fix: 공고 목록 메타데이터 한칸씩 밀림현상 수정

fix: 공고목록 밀림현상 재수정

-   `b25706e`
    -   feat: 공고문 원본 파일 다운로드 기능 추가,
    -   공고 마감일 시간(T10:00)텍스트 제거,
    -   사용자페이지 좌측 '용어 설명' 메뉴 삭제 및 네비게이션 비율 조정

### 2.2 관리자 서비스

관리자 Frontend는 쿠키 기반 관리자 인증 후 다음 기능을 제공한다.

-   공고 목록·상세 조회, 수집 상태 확인, 전체 수집 요청, 개별 공고 재수집
-   문서 목록·상세 조회, 처리·분석·다운로드 상태 확인, 파일 다운로드 및
    문서 재처리
-   단계별 오류 목록·상세 조회, 처리 상태 변경, 실패 단계 재시도
-   용어사전 조회·검색·등록·수정·삭제·활성 상태 변경
-   공고·문서·오류·용어사전 화면에서 공통 반응형 페이지네이션 사용

관리자 API 요청은 `credentials: 'include'`를 사용해 HttpOnly 쿠키 세션을
전달한다. 인증이 만료되어 API가 `401`을 반환하면 로그인 화면으로 이동한다.

## 3. 공고 상세 화면

공고 목록에서 특정 공고를 선택하면 상세 화면으로 이동한다.

상세 화면에서는 Backend에서 제공하는 공고 데이터를 기반으로 다음과 같은
정보를 표시한다.

``` text
공고 상세
│
├── 공고 기본 정보
├── 핵심 정보 요약
│   ├── 신청 일정
│   ├── 공급 위치
│   ├── 공급 내용과 단지·주택형별 상세 정보
│   ├── 신청 자격 요약과 대상별 상세 조건
│   ├── 소득/자산
│   ├── 제출 서류
│   └── 당첨자 발표
│
├── 상세 공고 내용
│
├── 원문 근거 보기
│
└── 공고문 원본 파일 다운로드
```

중요한 점은 Frontend가 핵심 정보를 직접 추출하는 것이 아니라 Backend가
제공한 데이터를 표시한다는 것이다.

## 4. 핵심 정보 카드

### 4.1 기능 목적

공고문은 일반적으로 내용이 길고 복잡하다.

따라서 사용자가 공고문 전체를 읽지 않아도 가장 먼저 확인해야 할 정보를
빠르게 파악할 수 있도록 핵심 정보 카드를 제공한다.

**예:**

핵심 정보 요약

신청 일정

2026-09-14 \~ 2026-09-18

공급 위치

전남광주통합특별시 순천시

공급 내용

...

신청 자격

...

소득/자산

...

제출 서류

...

당첨자 발표

2027-02-19

### 4.2 공급정보 상세 표시

`supply_information.housing_items`가 있으면 공급 정보 카드에 `자세히 보기`
버튼을 표시한다. 같은 `complex_name`을 가진 항목은 하나의 단지로 묶고,
그 안에서 주택형별 건설호수·공급호수·모집호수·모집인원·예비자 수를 표로
표시한다.

단지명이 없는 항목은 서로 합치지 않고 독립된 상세 공급정보로 유지한다.
또한 해당 단지의 모든 주택형에 값이 없는 필드는 표의 열에서도 제외해 빈
정보가 반복되지 않게 한다.

공급 위치는 핵심정보의 `location`을 우선 사용하고, 값이 없으면 공고의
`region`을 fallback으로 사용한다. 화면 영역에 따라 시·도 또는 시·군·구
수준으로 축약해 표시한다.

### 4.3 신청자격 상세 표시

신청자격 카드는 요약과 소득·자산 안내를 기본으로 표시한다. Backend가
공통 조건 또는 대상 그룹별 상세 조건을 제공할 때만 `자세히 보기` 버튼을
노출하며, 상세 내용은 카드 아래의 스크롤 가능한 영역에서 펼친다.

`income_asset_criteria.status`가 `not_found`이면 임의의 수치를 만들지 않고
공고문에 별도 기준이 명시되지 않았다는 안내 문구를 표시한다.

## 5. 핵심 정보 데이터 흐름

핵심 정보는 Frontend에서 문서를 분석하여 생성하지 않는다.

전체적인 데이터 흐름은 다음과 같다.

``` text
LH 공고문
   │
   ▼
문서 파싱
   │
   ▼
Structure 생성
   │
   ▼
```

핵심정보 추출

key_information_extractor.py

``` text
   │
   ▼
Backend / DB
   │
   ▼
상세 공고 API
   │
   ▼
```

DetailScreen.tsx

``` text
   │
   ▼
```

핵심 정보 카드

현재 확인된 key_information_extractor.py에서는 다음 7개 필드를
추출하도록 되어 있다.

-   `application_period`
-   `eligibility`
-   `supply_information`
-   `income_asset_criteria`
-   `required_documents`
-   `winner_announcement`
-   `contact_information`

따라서 Frontend에서 핵심 정보 카드의 정확도를 높이기 위해서는 화면에서
문자열을 임의로 잘라내는 방식보다 Backend/문서 구조화 단계에서 올바른
데이터가 만들어지는 것이 우선이다.

## 6. 핵심 정보 오류 사례

현재 발견된 대표적인 문제는 공급 내용에 공급 정보가 아닌 다음과 같은
내용이 들어오는 현상이다.

민감정보 수집 및 이용 동의 거부의 권리...

이 데이터는 Frontend에서 생성한 것이 아니다.

따라서 단순히 Frontend 코드를 수정해서 해결하는 것은 근본적인 해결
방법이 아니다.

현재 구조상 다음과 같이 접근해야 한다.

``` text
문서 원문
 ↓
문서 파싱
 ↓
Structure
 ↓
```

Section 분류

``` text
 ↓
Key Information Extraction
 ↓
DB
 ↓
Backend API
 ↓
Frontend
```

잘못된 정보가 DB/API까지 잘못 들어온다면 Frontend는 그것을 그대로
표시하게 된다.

## 7. 핵심 정보 정확도 개선 방향

현재 key_information_extractor.py는 Structure의 domain.category,
domain.topic을 우선 사용하고 이후 keyword를 fallback으로 사용하는
구조이다.

즉 다음과 같은 우선순위이다.

1순위

Structure domain.topic

``` text
        ↓ 실패
```

2순위

Structure domain.category

``` text
        ↓ 부족
```

3순위

Section title / 본문 keyword

이 구조는 방향 자체는 적절하다.

다만 단순 keyword 매칭만으로는 다음과 같은 문제가 발생할 수 있다.

-   공급 대상
-   공급 내용
-   신청 자격
-   소득 기준
-   개인정보 동의
-   제출 서류

처럼 서로 다른 Section이 비슷한 단어를 가지고 있기 때문이다.

따라서 정확도를 높일 때는 Frontend가 아니라 Structure 및 Extraction
단계의 Section 범위와 분류 정확도를 개선하는 것이 우선이다.

## 8. Frontend에서 해야 할 핵심 정보 관련 작업

Frontend에서는 Backend에서 전달받는 데이터가 정확하다는 전제하에 다음을
담당한다.

-   해야 하는 것
-   API 응답을 정확하게 화면에 매핑
-   값이 없는 경우 적절한 fallback
-   너무 긴 데이터의 UI 표시 방식 결정
-   핵심 정보 카드의 가독성 개선
-   데이터 타입에 맞는 UI 표시
-   날짜 표시 형식 정리
-   긴 텍스트의 줄바꿈 및 말줄임
-   잘못된 데이터가 들어왔을 때 UI가 깨지지 않도록 방어
-   하지 말아야 하는 것

Frontend에서 다음과 같은 방식으로 공고문을 다시 분석하는 것은 지양한다.

-   "개인정보"가 들어있으면 삭제
-   "공급"이라는 단어가 있으면 공급정보로 판단
-   문자열 길이가 길면 잘라서 사용

이런 처리는 데이터의 근본적인 문제를 숨기는 임시방편이 될 수 있다.

## 9. 원문 근거 보기

### 9.1 기능 목적

AI 챗봇이 답변을 생성했을 때 사용자가

"이 답변을 어디에서 가져온 거지?"

라는 의문을 가질 수 있다.

이를 해결하기 위해 챗봇 답변 하단에

원문 근거 보기

버튼을 제공한다.

사용자가 버튼을 누르면 AI 답변을 생성하는 데 사용된 근거 데이터를 확인할
수 있다.

## 10. 현재 원문 근거 보기의 구조

현재는 실제 PDF/HWP 원문을 그대로 화면에 표시하는 방식이 아니라 문서
파싱 과정에서 생성된 텍스트 청크를 근거로 표시하는 방식이다.

**현재 구조:**

``` text
사용자 질문
      ↓
Backend / RAG
      ↓
검색
      ↓
관련 Chunk
      ↓
LLM
      ↓
AI 답변
      ↓
근거 Chunk
      ↓
Frontend
      ↓
```

원문 근거 보기

따라서 현재의 "원문 근거"는 엄밀히 말하면 원본 문서 그 자체가 아니라
파싱된 텍스트 데이터의 근거 영역이다.

## 11. 원문 근거 보기 현재 구현

챗봇 응답의 `evidence` 배열을 모달에서 근거별 접이식 항목으로 표시한다.

-   기본 상태에서는 `근거 1`, `근거 2`와 문서의 section 제목을 표시한다.
-   항목을 펼치면 해당 근거의 파싱된 내용을 확인할 수 있다.
-   450자 또는 12줄을 넘는 긴 근거는 처음에 높이를 제한하고
    `전체 내용 보기`와 `접기` 버튼을 제공한다.
-   section 제목과 본문 첫 줄이 같으면 중복 제목을 제거한다.
-   줄바꿈과 특수 공백을 정규화해 긴 문장이 화면 밖으로 넘치지 않게 한다.

이 기능은 원본 PDF/HWP 파일 자체를 뷰어로 여는 것이 아니라 RAG가 답변에
참고한 파싱 문단을 읽기 좋게 보여주는 기능이다.

## 12. 향후 원문 근거 개선 시 중요한 부분

현재 UI 가독성 개선은 완료됐지만, 답변과 근거의 의미적 대응 정확도는
Backend/RAG가 반환하는 evidence 품질에 영향을 받는다. 단순히 Chunk를
짧게 자르는 것보다 다음 구조를 유지하는 것이 좋다.

``` text
사용자 질문
      ↓
검색된 Chunk
      ↓
답변에 실제 사용된 정보
      ↓
Evidence
      ├── source
      ├── section
      ├── text
      └── relevance
      ↓
Frontend
```

가능하다면 Backend에서 다음과 같은 형태의 데이터를 제공하는 것이 좋다.

``` json
{
"text": "신청기간은 2026년 9월 14일부터 9월 18일까지입니다.",
"source": {
"section": "신청일정"
}
}
```

Frontend는 이 데이터를 받아서 UI로 표현한다.

## 13. 챗봇

챗봇은 사용자가 공공임대/청약 공고에 대해 질문하면 Backend의 AI/RAG
시스템에서 생성한 답변을 화면에 표시하는 기능이다.

Frontend의 책임은 다음과 같다.

``` text
사용자 질문 입력
        ↓
Backend API 요청
        ↓
```

응답 대기

``` text
        ↓
AI 답변 표시
        ↓
```

근거 정보 표시

**Frontend가 직접 담당하지 않는 영역:**

-   문서 파싱
-   Chunking
-   Embedding
-   Vector Search
-   Retrieval
-   LLM 추론

이 부분들은 Backend/AI 파트의 책임이다.

## 14. 청약 용어 설명 기능

### 14.1 현재 접근 방식

기존에는 좌측 메뉴에 별도의

용어 설명

메뉴가 존재했고, 사용자가 해당 메뉴로 들어가면 청약 관련 용어를
카테고리별로 확인할 수 있었다.

현재 기본 사용자 흐름에서는 해당 좌측 메뉴를 제거했다. 대신 상세 화면이
`GET /api/glossary`로 활성 용어를 불러오고, AI 답변 안에서 일치하는 용어를
찾아 Tooltip으로 설명한다.

## 15. 챗봇 용어 Tooltip 현재 구현

AI 답변에 용어사전의 단어가 포함되면 파란색 밑줄로 표시하고, 마우스를
올렸을 때 용어명과 정의를 보여준다.

**AI 답변:**

신청자는 무주택세대구성원이어야 합니다.

여기서

무주택세대구성원

이라는 단어를 파란색 또는 밑줄 등으로 표시하고 마우스를 올리면 간단한
설명을 표시한다.

**예:**

무주택세대구성원

``` text
────────────────
```

세대원 전원이 주택을 소유하지 않은

세대의 구성원을 의미합니다.

`DetailScreen.tsx`는 용어를 긴 문자열부터 비교해 포함 관계가 있는 용어의
오탐을 줄인다. `GlossaryTooltip.tsx`는 `createPortal()`로 Tooltip을
`document.body`에 렌더링해 채팅 영역의 `overflow`에 잘리는 현상을
방지하며, 스크롤 시 Tooltip을 닫아 위치가 어긋나지 않게 한다.

목표는 사용자가 챗봇 답변을 읽다가 모르는 용어가 나왔을 때 별도의 검색이나
메뉴 이동 없이 바로 이해할 수 있도록 하는 것이다.

## 16. 용어사전 데이터 흐름

운영 용어사전 데이터는 Backend와 DB에서 관리한다.

**전체 구조:**

관리자

``` text
 ↓
관리자 용어사전 화면
 ↓
Backend API
 ↓
용어사전 DB
```

사용자 상세 화면의 AI 답변에는 다음과 같이 연결된다.

``` text
용어사전 DB
      ↓
Backend API
      ↓
```

Chatbot Response

``` text
      ↓
용어 인식
      ↓
Tooltip
      ↓
사용자
```

## 17. 독립 용어사전 화면 상태

`GlossaryScreen.tsx` 자체는 아직 임시 데이터를 사용한다.

**예:**

``` tsx
const glossaryDummyData = [
  {
    category: "청약/자격",
    term: "무주택 세대구성원",
    desc: "..."
  }
```

\]

따라서 독립 용어사전 화면은 UI 및 검색/카테고리 인터랙션 확인용 Dummy
Data 기반 구현이다. 이 상태와 별개로, 실제 AI 답변 Tooltip은 Backend의
`/api/glossary` 응답을 사용한다.

**현재 구현된 상태 관리:**

``` tsx
const [query, setQuery] = useState("");
const [activeTab, setActiveTab] = useState("전체");
```

검색은 용어명과 설명을 대상으로 수행하며 카테고리 필터도 함께 적용한다.

## 18. 용어사전 화면 구성

**현재 화면 구조:**

UserLayout

``` text
│
├── 목록으로 돌아가기
│
├── 청약 용어 사전
│
├── 검색창
│
├── 카테고리
│   ├── 전체
│   ├── 청약/자격
│   ├── 주택/유형
│   ├── 소득/자산
│   └── 기타
│
└── 용어 카드
    ├── 카테고리
    ├── 용어
    └── 설명
```

카테고리 선택 시 activeTab이 변경되고 해당 카테고리의 데이터만
필터링한다.

## 19. 관리자 용어사전

최근 작업에서는 관리자 페이지의 용어사전 기능도 Backend API와 연결하는
작업을 진행했다.

**관련 커밋:**

-   `a2b24c6`
    -   feat: 관리자 용어 사전 페이지 고도화 및 문서화 업데이트
-   `399c3ab`
    -   fix: 관리자 페이지 용어설명 데이터 라우트 재설정
-   `f28309e`
    -   fix: 관리자페이지 - 용어사전집DB api연동
-   `f98fcc2`
    -   fix: 관리자페이지 용어사전 목록 CRUD기능 작동수정
-   `0000edc`
    -   feat: 관리자 용어 사전 api통신 연동

현재 구조의 핵심은 다음과 같다.

``` text
관리자 Frontend
       ↓
HTTP API
       ↓
Backend
       ↓
용어사전 DB
```

관리자는 용어 데이터를 생성/조회/수정/삭제할 수 있도록 API 연동을
진행했다.

## 20. 공고문 원본 파일 다운로드

최근 Frontend에 공고문 원본 파일 다운로드 기능이 추가되었다.

**관련 커밋:**

-   `b25706e`
    -   feat: 공고문 원본 파일 다운로드 기능 추가

기본적인 목적은 사용자가 화면에 표시되는 요약 정보나 AI 답변만 확인하는
것이 아니라 필요한 경우 실제 공고문 파일을 직접 확인할 수 있도록 하는
것이다.

서비스 신뢰성 측면에서도 중요한 기능이다.

## 21. Frontend와 Backend 연결 관계

Frontend와 Backend는 기본적으로 HTTP API를 통해 통신하는 구조이다.

**기본적인 구조:**

**Frontend**

React / TypeScript

``` text
      │
      │ HTTP Request
      ▼
Backend
      │
      ├── DB
      ├── RAG
      ├── 문서 데이터
      └── 용어사전
```

Frontend에서 Backend의 Python 함수를 직접 import해서 사용하는 구조와는
구분해야 한다.

## 22. 연결 방식 구분

프로젝트에서 다른 파트와 연결될 때 반드시 다음을 구분한다.

``` text
HTTP API
Frontend → Backend
```

화면에서 필요한 데이터를 요청하거나 사용자의 질문을 전달할 때 사용한다.

**Python import**

``` text
Backend 내부
A.py → B.py
```

같은 Python 애플리케이션 내부 모듈 간 연결이다.

Frontend에서 직접 사용하는 방식이 아니다.

``` text
DB
Backend → DB
```

Frontend가 DB에 직접 접근하지 않고 Backend API를 통해 데이터를 받는 것을
기본 원칙으로 한다.

**파일**

``` text
Backend
 ↓
파일 경로 / 파일 URL
 ↓
Frontend
```

공고문 원본 다운로드 같은 기능에서 파일 위치와 접근 방식이 중요하다.

## 23. Frontend 데이터 흐름의 기본 원칙

Frontend에서는 다음 구조를 유지하는 것이 좋다.

``` text
사용자 행동
    ↓
```

화면 컴포넌트

``` text
    ↓
API 요청
    ↓
Backend
    ↓
```

JSON 응답

``` text
    ↓
State
    ↓
```

Component Rendering

반대로 다음 구조는 지양한다.

``` text
Frontend
 ↓
DB 직접 접근
```

또는

``` text
Frontend
 ↓
문서 원본 직접 파싱
```

또는

``` text
Frontend
 ↓
Backend 내부 Python 함수 직접 import
```

## 24. 주요 Frontend 구성 요소

현재 `frontend/`는 사용자와 관리자 애플리케이션이 각각 독립된 Vite
프로젝트로 구성된다.

``` text
Frontend
│
├── user
│   ├── src/components/layout/UserLayout.tsx
│   ├── src/components/common
│   │   ├── GlossaryTooltip.tsx
│   │   ├── Icons.tsx
│   │   ├── Pagination.tsx
│   │   └── StatusPill.tsx
│   ├── src/components/screens
│   │   ├── IntroScreen.tsx
│   │   ├── ListScreen.tsx
│   │   ├── DetailScreen.tsx
│   │   ├── GuideScreen.tsx
│   │   └── GlossaryScreen.tsx
│   ├── src/config.ts
│   ├── vite.config.ts
│   └── vercel.json
│
└── admin
    ├── src/components/Layout.tsx
    ├── src/components/Pagination.tsx
    ├── src/pages
    │   ├── Login.tsx
    │   ├── Announcement.tsx
    │   ├── Document.tsx
    │   ├── Error.tsx
    │   └── GlossaryAdmin.tsx
    ├── vite.config.ts
    └── vercel.json
```

## 25. UserLayout

UserLayout은 사용자 페이지에서 공통으로 사용하는 레이아웃 역할을 한다.

현재 GlossaryScreen에서도 다음과 같이 사용된다.

``` tsx
<UserLayout
  screen="glossary"
  go={go}
  showToast={showToast}
>
```

따라서 각 화면이 페이지 전체 레이아웃을 중복해서 구현하지 않고 공통
레이아웃을 사용할 수 있도록 구성되어 있다.

## 26. GlossaryScreen

GlossaryScreen은 청약 용어 사전을 표시하는 화면이다.

**주요 역할:**

``` text
용어사전 화면 생성
        ↓
검색어 State 관리
        ↓
카테고리 State 관리
        ↓
```

데이터 필터링

``` text
        ↓
용어 카드 렌더링
```

검색어는 query State에서 관리하고 카테고리는 activeTab State에서
관리한다.

## 27. 용어 검색 로직

현재 검색 로직은 다음과 같다.

``` text
사용자가 검색어 입력
        ↓
```

query 변경

``` text
        ↓
```

glossaryDummyData.filter()

``` text
        ↓
용어명 또는 설명에 검색어가 있는지 확인
        ↓
```

카테고리 조건 확인

``` text
        ↓
```

filteredData 생성

``` text
        ↓
```

화면 출력

코드상으로는 다음 조건을 사용한다.

``` tsx
const matchCategory =
  activeTab === "전체" ||
```

item.category === activeTab;

``` tsx
const matchQuery =
  item.term.includes(query) ||
```

item.desc.includes(query);

## 28. 용어사전 검색 결과 없음 처리

검색 결과가 없는 경우 별도의 Empty State를 표시한다.

검색된 용어가 없습니다

다른 검색어를 입력하거나

카테고리를 변경해 보세요.

이는 실제 API 데이터로 전환된 이후에도 유지할 수 있는 UI 패턴이다.

## 29. 현재 Frontend 개발 원칙

원칙 1. 화면과 데이터 처리를 분리

Frontend는 화면을 담당하고 Backend는 데이터 처리와 비즈니스 로직을
담당한다.

원칙 2. API 응답 구조를 기준으로 화면을 만든다

Backend에서 제공하는 JSON 구조를 기준으로 컴포넌트를 구성한다.

Frontend에서 임의로 데이터 구조를 만들어 Backend 데이터와 다른 형태로
관리하지 않는다.

원칙 3. 데이터 오류와 UI 오류를 구분한다

**예를 들어:**

공급 내용에 개인정보 문구가 들어옴

이것은 기본적으로 데이터 추출 문제이다.

**반면:**

공급 내용이 너무 길어서 카드가 깨짐

은 Frontend UI 문제이다.

문제 발생 위치를 먼저 구분해야 한다.

## 30. 현재 주요 작업 상태

| 기능 | 현재 상태 |
| --- | --- |
| 공고 목록·검색·필터·페이지 이동 | 구현 |
| 공고 상세·핵심 정보 카드 | 구현, 추출 데이터 정확도는 계속 검증 |
| 단지별 공급정보 상세 표 | 구현 |
| 신청자격 상세 펼침 | 구현 |
| AI 챗봇 | 구현 |
| 챗봇 근거 문단 보기 | 구현, 접이식·전체 보기 가독성 개선 완료 |
| AI 답변 용어 Tooltip | Backend 용어사전 API 연동 구현 |
| 공고문 원본 다운로드 | 구현 |
| 독립 사용자 용어사전 화면 | Dummy Data 기반 UI |
| 관리자 공고·문서·오류·용어사전 | API 연동 구현 |
| 관리자 실패 단계 재시도 | 구현 |
| 관리자 반응형 페이지네이션 | 구현, 560px 이하 5개·900px 이하 7개·그 외 10개 노출 |
| User/Admin Vercel 분리 배포 | 구현 |
| AWS Nginx HTTPS API 연결 | 구현 |
| Frontend CI 빌드 검사 | 구현 |

## 31. 현재 진행 중인 고도화 우선순위

현재 프로젝트에서는 단순히 기능을 많이 추가하기보다 사용자가 실제
서비스를 사용할 때 느끼는 신뢰성과 편의성을 높이는 방향을 우선한다.

우선순위는 다음과 같다.

### ★★★ 1. 핵심 정보 정확도

``` text
공고문
 ↓
Structure
 ↓
Key Information
 ↓
API
 ↓
Frontend
```

이 데이터 흐름에서 잘못된 정보가 생성되지 않도록 개선한다.

### ★★★ 2. 운영 환경 통합 검증

Vercel 사용자·관리자 화면에서 AWS API를 거쳐 공고 조회, 다운로드, 챗봇,
관리자 쿠키 인증 및 오류 재시도가 실제 운영 환경에서도 정상 동작하는지
확인한다.

### ★★★ 3. 구현 상태가 다른 용어 기능 구분

AI 답변 Tooltip은 Backend 용어사전 API와 연결되어 있다. 반면 독립 사용자
용어사전 화면은 Dummy Data 기반이므로 두 기능을 같은 완료 상태로 설명하지
않는다.

## 32. 용어 Tooltip 구현 및 유지보수 기준

Tooltip을 구현할 때 Frontend에서 모든 용어를 직접 하드코딩하는 방식은
피하는 것이 좋다.

**나쁜 예:**

``` tsx
if (text.includes("무주택세대구성원")) {
   ...
}
```

이 방식은 용어가 40개, 100개로 늘어날수록 유지보수가 어려워진다.

현재는 Backend에서 용어사전 데이터를 제공하고 Frontend가 해당 데이터를
활용한다.

**Backend**

``` json
{
  "term": "무주택세대구성원",
  "definition": "..."
}
```

``` text
↓
```

**Frontend**

``` text
↓
```

AI 답변의 해당 용어

``` text
↓
```

Tooltip 표시

## 33. Tooltip과 AI 답변의 연결

**현재 구현 형태:**

사용자

"제가 신청할 수 있나요?"

``` text
        ↓
```

Backend / RAG

``` text
        ↓
```

AI

"공고일 현재 무주택세대구성원이라면

신청할 수 있습니다."

``` text
        ↓
```

**Frontend**

무주택세대구성원

``` text
     ↑
```

hover

``` text
        ↓
```

Tooltip

"세대원 전원이 주택을 소유하지 않은

세대의 구성원을 의미합니다."

이렇게 구현하면 기존 용어사전 페이지로 이동하지 않고도 챗봇 안에서 바로
용어를 이해할 수 있다.

## 34. 현재 챗봇 UI와 향후 개선 기준

현재 챗봇은 단순 답변 텍스트와 함께 다음 구조를 제공한다.

``` text
AI 답변
│
├── 답변 내용
│
├── 어려운 용어 Tooltip
│
└── 원문 근거 보기
        │
        └── 핵심 Evidence
```

사용자 입장에서는

``` text
답변
 ↓
모르는 용어 → 바로 설명
 ↓
답변이 맞는지 궁금함 → 근거 확인
 ↓
더 자세히 보고 싶음 → 원본 다운로드
```

라는 자연스러운 흐름이 만들어진다.

## 35. 공고 상세 화면의 데이터 신뢰성

공고 상세 화면에서 가장 중요한 부분은 Backend 데이터와 화면의 매핑이
정확한지 확인하는 것이다.

예를 들어 Backend가

``` json
{
"application_period": "...",
"eligibility": "...",
"supply_information": "..."
}
```

를 반환한다면 Frontend는 각각의 필드를 정확히 대응시켜야 한다.

application_period

``` text
       ↓
```

신청 일정

eligibility

``` text
       ↓
```

신청 자격

supply_information

``` text
       ↓
```

공급 내용

필드 순서에 의존해서 데이터를 표시하면 안 된다.

최근 공고 목록에서 발생했던 한 칸씩 밀림 현상도 이런 데이터 매핑 문제를
점검할 때 반드시 확인해야 하는 사례이다.

## 36. 날짜 데이터 처리

Backend에서 날짜가 다음과 같이 전달될 수 있다.

2026-09-18T10:00

사용자 화면에서는 내부 데이터 형식을 그대로 노출하지 않고 서비스 UI에
적합한 형태로 표시해야 한다.

**예:**

2026-09-18 10:00

또는

2026년 9월 18일 오전 10시

현재 작업에서는 공고 마감일의 T10:00과 같은 불필요한 텍스트가 화면에
그대로 표시되는 문제를 수정했다.

## 37. 오류 처리

Frontend는 API 요청이 항상 성공한다고 가정하면 안 된다.

최소한 다음 상태를 고려한다.

Loading

``` text
   ↓
```

Success

``` text
   ↓
```

Empty

``` text
   ↓
```

Error

**예:**

공고 데이터 로딩 중...

공고가 없습니다.

공고 데이터를 불러오지 못했습니다.

잠시 후 다시 시도해주세요.

## 38. 실행 시 Frontend 확인 순서

개발자가 프로젝트를 실행할 때는 다음 순서로 확인하는 것을 권장한다.

## 1. Frontend 실행

``` text
        ↓
```

## 2. Backend 실행 여부 확인

``` text
        ↓
```

## 3. API 요청 확인

``` text
        ↓
```

## 4. 공고 목록 확인

``` text
        ↓
```

## 5. 공고 상세 확인

``` text
        ↓
```

## 6. 핵심 정보 확인

``` text
        ↓
```

## 7. 챗봇 질문

``` text
        ↓
```

## 8. 답변 확인

``` text
        ↓
```

## 9. 원문 근거 보기 확인

``` text
        ↓
```

## 10. 용어사전/관리자 기능 확인

## 39. API 문제와 Frontend 문제 구분

화면에 데이터가 나오지 않을 경우 바로 React 코드부터 수정하지 않는다.

다음 순서로 확인한다.

## 1. API 요청이 발생했는가?

``` text
        ↓
```

## 2. HTTP Status가 정상인가?

``` text
        ↓
```

## 3. Response JSON이 정상인가?

``` text
        ↓
```

## 4. 원하는 필드가 존재하는가?

``` text
        ↓
```

## 5. Frontend State에 들어왔는가?

``` text
        ↓
```

## 6. Component에서 올바른 필드를 사용하고 있는가?

이 과정을 거치면 문제 위치를 빠르게 찾을 수 있다.

## 40. 핵심 정보 문제 발생 시 확인 순서

현재 프로젝트에서 특히 중요한 부분이다.

**예를 들어:**

공급 내용

``` text
→ 개인정보 동의 문구가 출력됨
```

이라면 다음 순서로 확인한다.

``` text
① DB 값 확인
        ↓
② Backend API Response 확인
        ↓
③ Frontend에서 받은 값 확인
        ↓
```

④ key_information 데이터 확인

``` text
        ↓
```

⑤ key_information_extractor.py 확인

``` text
        ↓
⑥ Structure JSON 확인
        ↓
```

⑦ 해당 Section의 domain/category/topic 확인

``` text
        ↓
⑧ 원본 문서 확인
```

만약 DB/API 단계부터 잘못되어 있다면 Frontend 수정 대상이 아니다.

## 41. 현재 문서 파싱 파트와의 연결

Frontend에서 핵심 정보 데이터를 직접 생성하지 않는다.

문서 파싱 담당 파트에서

HWP / HWPX / PDF

``` text
        ↓
Parsing
        ↓
Structure
        ↓
Normalization
        ↓
Verification
        ↓
Key Information Extraction
```

을 수행하고 결과가 Backend 데이터로 전달된다.

Frontend는 최종 결과를 받아 사용자에게 표시한다.

따라서 핵심 정보 오류를 수정할 때 Frontend 담당자와 문서 파싱 담당자가
함께 데이터 흐름을 확인해야 한다.

## 42. key_information_extractor.py와 Frontend의 관계

현재 공유된 Extractor는 Structure의 Section을 순회하면서 각 필드에
적합한 Section을 점수화한다.

**개념적으로:**

``` text
Structure Section
       ↓
```

FIELD_RULES

``` text
       ↓
```

-   `category`
-   `topic`
-   `keyword`

``` text
       ↓
```

score

``` text
       ↓
```

field별 match

``` text
       ↓
```

key_information

그리고 최종적으로 다음 데이터를 만든다.

-   `application_period`
-   `eligibility`
-   `supply_information`
-   `income_asset_criteria`
-   `required_documents`
-   `winner_announcement`
-   `contact_information`

따라서 Frontend에서 핵심 정보의 정확도를 높이는 작업은 다음과 같이
역할을 구분해야 한다.

``` text
문서 파싱/Extraction
→ "어떤 데이터를 추출할 것인가"
```

``` text
Backend
→ "어떤 데이터를 저장하고 어떻게 제공할 것인가"
```

``` text
Frontend
→ "받은 데이터를 어떻게 정확하고 읽기 좋게 보여줄 것인가"
```

## 43. 현재 프로젝트의 책임 범위

``` text
┌────────────────────────────┐
│ Crawler                    │
│ 공고 수집 / 파일 다운로드   │
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Document Parsing           │
│ HWP/HWPX/PDF 파싱          │
│ Structure 생성             │
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Key Information Extraction │
│ 핵심정보 추출              │
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Backend / DB               │
│ 저장 / API 제공            │
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Frontend                   │
│ 화면 표시                  │
└────────────────────────────┘
```

## 44. 현재 배포와 Docker 분리 상태

Docker 분리는 향후 계획이 아니라 현재 AWS 운영 구조에 반영되어 있다.
다만 Frontend는 Docker에 포함하지 않고 User와 Admin을 각각 Vercel에
배포한다.

``` text
사용자 브라우저
   │
   ├── https://ddokbot.codefoilo.store
   │        └── Vercel User Frontend
   │
   └── https://ddokbot.admin.codefoilo.store
            └── Vercel Admin Frontend
                     │
                     │ /api/* rewrite
                     ▼
          https://ddokbot-api.hwanmade.store
                     │
                     ▼
              Docker Nginx :443
                     │
                     ▼
              Docker Backend :18000
```

AWS의 주요 서비스는 `infra/docker-compose.yml`에서 `backend`, `scheduler`,
`crawler`, `document-worker`, `embedding`, `rag`, `llm`, `postgres`, `nginx`
컨테이너로 분리되어 있다. Docker 내부 호출은 `localhost`가 아니라
`crawler:8000`, `document-worker:18003`, `rag:18002`처럼 Compose 서비스
이름을 사용한다.

Nginx는 80번 HTTP 요청을 HTTPS로 전환하고, 443번에서 Cloudflare Origin
인증서를 사용한다. `/api/` 요청은 Docker 내부 `backend:18000`으로 전달하며,
`/nginx-health`는 프록시 컨테이너 상태 확인에 사용한다. 인증서와 개인키는
이미지나 Git에 포함하지 않고 운영 Host 경로를 읽기 전용으로 마운트한다.

### 44.1 Vercel 배포 설정

-   `frontend/user/vercel.json`: `/api/:path*`를 AWS API 도메인으로 rewrite
-   `frontend/admin/vercel.json`: 동일 API rewrite와 React Router용
    `/:path* → /index.html` SPA fallback 적용
-   Frontend 코드는 상대경로 `/api`를 사용하므로 브라우저는 Vercel
    도메인의 같은 Origin으로 요청하고, Vercel이 AWS API로 전달한다.
-   Admin은 `credentials: 'include'`로 인증 쿠키를 포함한다.

### 44.2 CI/CD

`.github/workflows/ci.yml`은 `develop-api`와 `main`의 push/PR에서 User와
Admin 각각 `npm ci`와 build를 실행하고, Admin lint와 Python·Compose 검사도
함께 수행한다.

`.github/workflows/deploy-aws.yml`은 `main` CI 성공 후 또는 수동 실행 시
AWS 코드를 갱신하고 Docker 이미지 빌드, DB migration, 서비스 재기동과
내부·외부 health check를 수행한다. 이 Workflow는 AWS 서비스 배포용이며,
Vercel Frontend 배포는 각 Vercel 프로젝트의 Git 연동 설정에서 관리한다.

## 45. API 주소 관리

User Frontend의 API Base URL은 `frontend/user/src/config.ts`의 `/api`를
사용한다. 로컬 Vite 개발 서버는 이 경로를 `http://127.0.0.1:18000`으로
프록시하고, Vercel 운영 환경은 `vercel.json`에서
`https://ddokbot-api.hwanmade.store`로 rewrite한다.

Admin Frontend도 상대경로 `/api`를 사용한다. 따라서 컴포넌트에 AWS IP나
Docker 서비스 주소를 직접 작성하지 않는다. `backend:18000` 같은 이름은
Nginx와 Backend가 같은 Docker Network에서 통신할 때만 사용하며 브라우저에
노출하지 않는다.

## 46. 파일 경로 의존성

공고문 원본 다운로드 기능에서 Frontend가 Backend 서버의 실제 로컬 파일
경로를 직접 알고 있으면 Docker 분리 이후 문제가 발생할 수 있다.

**지양:**

C:`\project`{=tex}`\files`{=tex}`\announcement`{=tex}.pdf

**권장:**

``` text
Frontend
 ↓
Backend API / 파일 URL
 ↓
Backend
 ↓
파일
```

Frontend는 서버 내부의 실제 파일 시스템 경로를 알 필요가 없어야 한다.

## 47. 현재 구조에서 중요한 데이터 경계

각 파트의 책임을 다음과 같이 유지한다.

``` text
Crawler
→ 수집
```

``` text
Parser
→ 파싱
```

``` text
Structure
→ 구조화
```

``` text
Extractor
→ 핵심정보 추출
```

``` text
Backend
→ 저장 / API
```

``` text
Frontend
→ 표현
```

이 경계를 명확하게 유지하면 나중에 Docker로 각각 분리하더라도 구조를
이해하기 쉽다.

## 48. 개발자가 새로운 기능을 추가할 때

새로운 기능을 추가할 때 먼저 다음 질문을 한다.

이 기능은 데이터를 어디에서 가져오는가?

-   Backend API인가?
-   DB인가?
-   파일인가?

데이터를 누가 생성하는가?

Frontend가 직접 처리해야 하는가?

Backend에서 처리해야 하는가?

다른 파트와 어떤 방식으로 연결되는가?

**예를 들어 챗봇 Tooltip 기능이라면:**

``` text
용어 데이터
→ Backend / DB
```

``` text
챗봇 답변
→ Backend API
```

``` text
Tooltip UI
→ Frontend
```

으로 역할을 나누는 것이 적절하다.

## 49. 현재 고도화 작업의 큰 방향

현재 Frontend 고도화의 핵심은 기능 개수 증가보다 사용자 경험과 신뢰성
개선이다.

**우선 개선 대상:**

① 핵심 정보가 정확하게 표시되는가?

``` text
        ↓
② AI 답변의 근거를 이해하기 쉽게 볼 수 있는가?
        ↓
③ 어려운 청약 용어를 바로 이해할 수 있는가?
        ↓
④ 공고 원문을 쉽게 확인할 수 있는가?
```

이 네 가지가 서로 연결되어 있다.

## 50. 현재 사용자 경험

현재 사용자가 서비스를 이용하는 기본 흐름은 다음과 같다.

``` text
공고 검색
   ↓
공고 선택
   ↓
```

핵심 정보 확인

``` text
   ↓
```

궁금한 내용 질문

``` text
   ↓
AI 답변
   ↓
모르는 용어 → Tooltip
   ↓
답변 근거 → 원문 근거 보기
   ↓
```

더 자세한 확인 필요

``` text
   ↓
공고문 원본 다운로드
```

이 구조를 통해 사용자는 공고문 전체를 처음부터 끝까지 읽기 전에 필요한
핵심정보와 관련 근거를 먼저 확인할 수 있다.

## 51. 개발 시 가장 중요한 판단 기준

이 프로젝트의 Frontend 개발에서 중요한 것은

"화면에 무엇을 많이 보여주는가"가 아니라 "사용자가 필요한 정보를 얼마나
빠르고 정확하게 이해할 수 있는가"이다.

따라서 다음을 우선한다.

정확성

``` text
>
```

가독성

``` text
>
```

사용 편의성

``` text
>
```

기능 추가

특히 공공임대/청약 정보는 잘못된 정보를 보여주는 것이 단순 UI 오류보다
훨씬 큰 문제가 될 수 있으므로 데이터 정확성을 우선한다.

## 52. 현재 주요 작업 기록

**최근 Frontend 작업 흐름:**

2026-08-25

``` text
│
└── 관리자 용어사전 페이지 고도화
    및 문서화
```

2026-08-26

``` text
│
├── 관리자 용어사전 데이터 라우트 수정
├── 용어사전 DB API 연동
└── 관리자 용어사전 CRUD 수정
```

2026-08-27

``` text
│
├── 관리자 용어사전 API 통신 연동
├── 공고문 원본 다운로드 기능 추가
├── 공고 마감일 T10:00 표시 문제 수정
├── 사용자 용어 설명 메뉴 제거
├── 네비게이션 비율 조정
└── 공고 목록 데이터 밀림 문제 수정
```

2026-08-31 ~ 2026-09-01

``` text
│
├── AI 답변 용어 Tooltip 잘림 현상 수정
├── 공고 목록 날짜 가독성 개선
├── 신청자격 상세 펼침 기능 추가
└── User/Admin 서비스 제목 정리
```

2026-09-03 ~ 2026-09-05

``` text
│
├── 공고 지역 표시 및 원문 다운로드 연동 보완
├── 관리자 실패 문서 단계별 재시도 UI 연동
└── 전체 수집·Publish·Collection 보관 구조와 연동
```

2026-09-07 ~ 2026-09-11

``` text
│
├── 관리자 공통 반응형 페이지네이션 적용
├── Docker Nginx API 리버스 프록시와 HTTPS 적용
├── User/Admin Vercel 배포 설정 추가
├── 공급정보 상세 표와 신청자격 상세 UI 개선
└── GitHub Actions CI 및 AWS CD 추가
```

2026-09-12 ~ 2026-09-14

``` text
│
├── 같은 complex_name의 주택형을 단지별로 그룹화
├── 빈 공급 위치의 공고 지역 fallback 처리
├── 소득·자산 상태별 안내 문구 보완
└── 답변 근거 모달의 접기·펼치기와 긴 문단 가독성 개선
```

## 53. 최근 커밋 기준 작업 이력

**문서 작성 이후 주요 커밋:**

-   `6d483e2`: AI 답변 용어 Tooltip 잘림 현상 수정
-   `55b2f97`: 신청자격 상세 버튼 추가
-   `b0f88fa`: 공고 지역 표시 개선 및 공고문 다운로드 구현
-   `b5ae3a3`: 관리자 페이지네이션 반응형 개선
-   `5b63b49`: Docker Nginx API 리버스 프록시 추가
-   `ffe6fb0`: Nginx HTTPS 및 Cloudflare Origin 인증서 연동
-   `385b443`: User/Admin Vercel 배포 설정 추가
-   `01ba5e5`: 공급정보 상세 표 및 신청자격 패널 개선
-   `ad9e50a`: AWS 배포 Workflow 추가
-   `892c4d9`: 공고 상세 공급정보 및 자격조건 표시 개선
-   `fc79790`: 공급 위치 축약 및 소득·자산 안내 문구 개선
-   `ed506b1`: 빈 공급 위치의 지역 fallback 처리
-   `2f77510`: 답변 근거 보기 가독성 개선

**기존 기록:**

-   `0000edc`
    -   feat: 관리자 용어 사전 api통신 연동
-   `f98fcc2`
    -   fix: 관리자페이지 용어사전 목록 CRUD기능 작동수정
-   `f28309e`
    -   fix: 관리자페이지 - 용어사전집DB api연동
-   `399c3ab`
    -   fix: 관리자 페이지 용어설명 데이터 라우트 재설정
-   `a2b24c6`
    -   feat: 관리자 용어 사전 페이지 고도화 및 문서화 업데이트
-   `b25706e`
    -   feat: 공고문 원본 파일 다운로드 기능 추가,
    -   공고 마감일 시간(T10:00)텍스트 제거,
    -   사용자페이지 좌측 '용어 설명' 메뉴 삭제 및
    -   네비게이션 비율 조정
-   `f33632a`
    -   fix: 공고 목록 메타데이터 한칸씩 밀림현상 수정

fix

공고목록 밀림현상 재수정

## 54. 현재 한계

현재 MVP 단계에서 알고 있어야 하는 구조적인 한계는 다음과 같다.

**핵심 정보**

문서 파싱/Extraction 결과에 따라 정확도가 달라진다.

**원문 근거**

현재 실제 원본 PDF/HWP를 직접 보여주는 것이 아니라 파싱된 Chunk
기반이다.

**용어 Tooltip**

AI 답변과 Backend 용어사전은 연결됐지만 독립 사용자 용어사전 화면은 아직
Dummy Data를 사용한다.

**API**

일부 기능은 Backend API 개발 상태에 따라 Frontend 구현 상태가 달라질 수
있다.

**운영환경**

Frontend는 Vercel, API는 Cloudflare와 AWS Nginx를 거치므로 로컬에서
정상인 기능도 운영 환경의 rewrite, 쿠키, HTTPS 설정을 포함해 종단 검증해야
한다. AWS Docker 서비스와 Vercel Git 연동 상태는 배포 변경 시 함께
확인한다.

## 55. 새로운 팀원이 가장 먼저 이해해야 하는 것

이 프로젝트에 처음 참여한 개발자는 먼저 다음 구조를 이해하면 된다.

``` text
[공고 수집]
```

LH/SH 등

``` text
   ↓
[Crawler]
   ↓
[문서 파일]
   ↓
[문서 파싱]
   ↓
[Structure]
   ↓
[핵심정보 추출]
   ↓
[Backend / DB]
   ↓
[Frontend]
   ↓
사용자 화면
```

그리고 AI 챗봇은 별도의 흐름으로

``` text
사용자 질문
   ↓
Backend
   ↓
검색/RAG
   ↓
근거 Chunk
   ↓
LLM
   ↓
AI 답변
   ↓
Frontend
```

으로 동작한다고 이해하면 된다.

## 56. 문제를 발견했을 때의 기본 원칙

화면에 이상한 데이터가 보였다고 해서 무조건 Frontend 문제라고 판단하지
않는다.

**예:**

화면에 이상한 공급 내용이 출력됨

이라면

``` text
Frontend 문제인가?
        ↓
API Response 확인
        ↓
API가 이미 잘못됐나?
        ↓
DB 확인
        ↓
Extractor 확인
        ↓
Structure 확인
```

과 같이 데이터가 처음 잘못 생성된 지점을 찾는 방식으로 디버깅한다.

## 57. 파트 간 협업 시 전달해야 하는 정보

다른 팀원에게 문제를 전달할 때는 단순히

"프론트에서 이상하게 나와요."

라고 전달하지 않는다.

다음과 같이 전달한다.

**\[문제\]** 공고 상세 핵심정보의 공급 내용에

개인정보 동의 관련 문장이 표시됨.

**\[Frontend 확인\]** API Response 단계부터 동일한 데이터가 내려옴.

**\[추정 원인\]** - Frontend 렌더링 문제가 아니라 - key_information
extraction 단계에서 - 잘못된 Section이 supply_information으로

매핑된 것으로 추정.

**\[확인 요청\]** Structure Section의 domain.category/topic과

supply_information scoring 결과 확인 필요.

이렇게 전달하면 담당자가 훨씬 빠르게 원인을 찾을 수 있다.

## 58. Frontend 담당자의 최종 책임

Frontend 담당자의 핵심 책임은 다음과 같다.

``` text
Backend가 제공한 데이터를
        ↓
```

정확하게 받고

``` text
        ↓
```

올바른 UI에 매핑하고

``` text
        ↓
사용자가 이해하기 쉽게 표시하며
        ↓
사용자 행동에 적절하게 반응하도록 만드는 것
```

그리고 데이터의 품질 문제가 발생하면 해당 데이터가 생성되는 담당 파트와
협업하여 원인을 찾아야 한다.

## 59. 향후 개발 시 체크리스트

새로운 기능을 구현하기 전에 다음을 확인한다.

-   [ ] 이 기능은 어느 파트의 책임인가?

-   [ ] 필요한 데이터는 어디에서 생성되는가?

-   [ ] Backend API가 존재하는가?

-   [ ] API 요청/응답 구조를 확인했는가?

-   [ ] Frontend가 직접 처리해야 하는 로직인가?

-   [ ] DB에 직접 접근하고 있지는 않은가?

-   [ ] localhost 주소에 의존하고 있지는 않은가?

-   [ ] Docker 분리 후에도 동작할 수 있는 구조인가?

-   [ ] API 오류 / 빈 데이터 상태를 처리했는가?

-   [ ] 사용자가 실제로 이해하기 쉬운 UI인가?

## 60. 최종 프로젝트 구조 이해

이 프로젝트의 전체적인 구조를 한 문장으로 정리하면 다음과 같다.

공공임대/청약 공고문을 수집하고 문서 구조화 및 AI/RAG 처리를 거쳐
사용자가 복잡한 공고 정보를 쉽게 이해하고 질문할 수 있도록 제공하는
서비스이며, Frontend는 이 데이터와 AI 결과를 사용자 친화적인 화면으로
제공하는 역할을 담당한다.

Frontend에서는 특히 다음 네 가지 경험을 연결하는 것이 중요하다.

**핵심 정보**

``` text
   +
AI 챗봇
   +
```

근거 보기

``` text
   +
용어 Tooltip
   ↓
사용자가 공고문을
```

쉽게 이해하고 신뢰할 수 있는 서비스

문서 작성 시 주의

이 문서에서 확정된 사실과 향후 구현 예정인 기능을 구분하는 것이
중요하다.

**현재 구현:**

-   공고 상세
-   핵심 정보 카드
-   단지·주택형별 공급정보 상세 표
-   신청자격 상세 펼침
-   AI 챗봇
-   접이식 근거 문단 보기
-   AI 답변 용어 Tooltip
-   공고문 다운로드
-   관리자 용어사전 API 연동
-   관리자 공고·문서·오류 관리와 단계별 재시도
-   관리자 반응형 페이지네이션
-   User/Admin Vercel 분리 배포
-   Docker Nginx HTTPS API 프록시
-   Frontend CI와 AWS CD

**진행/고도화:**

-   핵심정보 정확도 개선
-   답변과 근거 데이터의 의미적 대응 품질 개선
-   독립 사용자 용어사전의 실제 API 전환 여부 결정
-   Vercel → AWS API, 관리자 쿠키 인증 및 전체 서비스 운영 종단 검증

따라서 후임자가 이 문서를 읽고 "문서에 적혀 있으니 이미 완성된
기능이겠구나"라고 오해하지 않도록, 진행 중인 기능은 반드시 진행 중,
고도화 예정, Backend 연동 예정 등의 상태를 함께 표시한다.

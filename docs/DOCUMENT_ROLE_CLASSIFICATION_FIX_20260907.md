# 문서 역할 분류 보완 기록

## 발생 일시

- 2026-09-07 12:00 KST 정기 전체 수집

## 실행 결과

- Scheduler 정기 실행: 정상
- CollectionRun: 17
- 공고 수집: 50건 성공
- 저장 문서: 83건
- 분석 대상 primary 문서: 45건
- 문서 처리: 45건 성공, 0건 실패
- Publish: 실패
- 기존 활성 CollectionRun 16 유지
- 기존 직전 CollectionRun 15 유지

## 원인

부속 문서 4건이 `unknown`으로 분류되어 Publish 검증이 차단됐다.

대표 파일:

```text
[양식1]부천권_국민임대_서류제출대상자서류양식.hwpx
```

해당 파일은 부속 문서이지만 기존 키워드 `제출서류`와 문자열 순서가 달라 분류되지 않았다.

## 수정 내용

`SUPPORTING_KEYWORDS`에 다음 항목을 추가한다.

- `서류양식`
- `고객메뉴얼`
- `고객매뉴얼`
- `행정정보제공요구서`

`unknown` 문서의 Publish 차단 정책은 유지한다.

## 검증 결과

- 문서 역할 및 전체 수집 정책 테스트: 40 passed
- 실제 파일명 분류 subtest: 4 passed
- Ruff: 통과
- `git diff --check`: 통과

## 배포 및 재검증

- Backend 이미지 재빌드
- Backend 및 Scheduler 컨테이너 재생성
- 기존 Run 17은 실패 이력으로 유지
- 다음 전체 수집에서 부속 문서가 `supporting`으로 저장되는지 확인
- 새 CollectionRun이 정상 Publish되는지 확인

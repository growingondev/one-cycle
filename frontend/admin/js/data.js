
export const notices=[
{id:1,title:'[정정공고] 고양창릉 S-4블록 공공분양 입주자모집공고',region:'경기',noticeDate:'2026-08-05',status:'공고중',collect:'수집완료'},
{id:2,title:'역곡지구 A-2블록 신혼희망타운 입주자모집공고',region:'경기',noticeDate:'2026-08-04',status:'접수중',collect:'수집완료'},
{id:3,title:'인천검단 AA21블록 공공분양 추가모집공고',region:'인천',noticeDate:'2026-08-02',status:'공고중',collect:'수집완료'},
{id:4,title:'화성동탄2 C-14블록 공공분양 입주자모집공고',region:'경기',noticeDate:'2026-07-30',status:'마감',collect:'수집완료'},
{id:5,title:'남양주왕숙 A-24블록 공공분양 사전청약 공고',region:'경기',noticeDate:'2026-07-28',status:'마감',collect:'수집실패'},
{id:6,title:'부산명지 B-3블록 공공분양 입주자모집공고',region:'부산',noticeDate:'2026-07-25',status:'마감',collect:'수집완료'},
{id:7,title:'대전도안 2-5블록 공공분양 입주자모집공고',region:'대전',noticeDate:'2026-07-22',status:'마감',collect:'수집완료'}];
export const documents=[
{id:1,notice:'고양창릉 S-4블록',name:'고양창릉_S4_입주자모집공고.hwpx',type:'공고문',size:'4.8 MB',date:'2026-08-05',process:'처리완료',analysis:'분석완료'},
{id:2,notice:'고양창릉 S-4블록',name:'고양창릉_S4_정정공고.hwpx',type:'정정공고문',size:'4.9 MB',date:'2026-08-05',process:'처리완료',analysis:'분석완료'},
{id:3,notice:'역곡지구 A-2블록',name:'역곡_A2_모집공고.hwp',type:'공고문',size:'3.7 MB',date:'2026-08-04',process:'처리완료',analysis:'분석완료'},
{id:4,notice:'인천검단 AA21블록',name:'검단_AA21_추가모집.hwpx',type:'공고문',size:'5.3 MB',date:'2026-08-02',process:'처리중',analysis:'대기'},
{id:5,notice:'남양주왕숙 A-24블록',name:'왕숙_A24_사전청약.hwp',type:'공고문',size:'6.1 MB',date:'2026-07-28',process:'처리실패',analysis:'분석실패'},
{id:6,notice:'부산명지 B-3블록',name:'명지_B3_제출서류.pdf',type:'첨부문서',size:'1.4 MB',date:'2026-07-25',process:'처리완료',analysis:'분석완료'}];
export const errors=[
{id:1,time:'2026-08-07 09:15',type:'문서 처리',step:'HWP 파싱',target:'남양주왕숙 A-24블록',message:'표 병합 셀 구조를 해석하지 못했습니다.',status:'미해결'},
{id:2,time:'2026-08-06 16:42',type:'공고 수집',step:'첨부파일 다운로드',target:'인천검단 AA21블록',message:'원문 서버 응답 시간이 초과되었습니다.',status:'해결중'},
{id:3,time:'2026-08-06 14:10',type:'AI 분석',step:'임베딩',target:'역곡지구 A-2블록',message:'일시적인 GPU 메모리 부족이 발생했습니다.',status:'해결완료'},
{id:4,time:'2026-08-05 11:30',type:'문서 처리',step:'구조화',target:'고양창릉 S-4블록',message:'일부 문단의 제목 계층을 식별하지 못했습니다.',status:'해결완료'},
{id:5,time:'2026-08-04 18:22',type:'공고 수집',step:'상세 수집',target:'화성동탄2 C-14블록',message:'상세 페이지 URL 형식이 변경되었습니다.',status:'미해결'}];

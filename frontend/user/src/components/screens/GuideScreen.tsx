import { Search, MessageSquare, CheckCircle2, ChevronRight, ChevronDown, ArrowRight } from "lucide-react";
import { UserLayout } from "../layout/UserLayout";
import { Icon } from "../common/Icons";

export function GuideScreen({ go, showToast }: { go: (s: any) => void; showToast: (m: string) => void; }) {
  return (
    <UserLayout screen="guide" go={go} showToast={showToast}>
      <button className="flex items-center gap-1.5 text-sm font-bold text-slate-600 hover:text-slate-900 mb-4 transition-colors" onClick={() => go("list")}>
        <Icon name="back" size={16} /> 목록으로 돌아가기
      </button>

      <section className="mb-8 lg:mb-10 text-center lg:text-left">
        <h1 className="text-[26px] lg:text-[32px] font-extrabold text-slate-900 tracking-tight leading-tight">이용 안내</h1>
        <p className="text-[15px] lg:text-[17px] text-slate-500 mt-2">LH 공고 AI 도우미를 3단계로 쉽고 빠르게 활용해 보세요.</p>
      </section>

      {/* 단계별 플로우 컨테이너 */}
      <div className="flex flex-col lg:flex-row items-center justify-between gap-4 lg:gap-6 bg-slate-50/50 p-6 lg:p-10 rounded-2xl border border-slate-200">
        
        {/* Step 1: 클릭 시 공고 목록으로 이동하도록 수정 */}
        <div 
          onClick={() => { go("list"); showToast("공고 목록으로 이동합니다."); }}
          className="flex-1 w-full bg-white border border-slate-200 rounded-2xl p-6 lg:p-8 shadow-sm hover:shadow-md hover:border-blue-400 transition-all relative overflow-hidden group cursor-pointer"
        >
          <div className="absolute top-0 right-0 w-24 h-24 bg-blue-50 rounded-bl-full -z-10 group-hover:scale-110 transition-transform"></div>
          <div className="w-14 h-14 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 mb-5">
            <Search size={28} />
          </div>
          <h2 className="text-blue-600 font-black text-sm lg:text-base mb-1">STEP 1</h2>
          <h3 className="text-xl lg:text-2xl font-bold text-slate-900 mb-3">공고 검색 및 선택 ➔</h3>
          <p className="text-[14px] lg:text-[15px] text-slate-600 leading-relaxed break-keep">
            메인 화면의 공고 목록에서 지역이나 상태를 필터링하여 내가 관심 있는 청약 공고를 클릭하세요. (여기를 눌러 이동하기)
          </p>
        </div>

        {/* 화살표 */}
        <div className="text-slate-300 flex-shrink-0 animate-pulse">
          <ChevronDown size={40} className="block lg:hidden" />
          <ChevronRight size={40} className="hidden lg:block" />
        </div>

        {/* Step 2 */}
        <div className="flex-1 w-full bg-white border border-slate-200 rounded-2xl p-6 lg:p-8 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-50 rounded-bl-full -z-10"></div>
          <div className="w-14 h-14 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 mb-5">
            <MessageSquare size={28} />
          </div>
          <h2 className="text-indigo-600 font-black text-sm lg:text-base mb-1">STEP 2</h2>
          <h3 className="text-xl lg:text-2xl font-bold text-slate-900 mb-3">AI에게 질문하기</h3>
          <p className="text-[14px] lg:text-[15px] text-slate-600 leading-relaxed break-keep">
            우측 채팅창에 "내 소득으로 신청 가능한가요?", "필요한 서류가 뭐야?" 와 같이 일상적인 언어로 자유롭게 질문해 보세요.
          </p>
        </div>

        {/* 화살표 */}
        <div className="text-slate-300 flex-shrink-0 animate-pulse">
          <ChevronDown size={40} className="block lg:hidden" />
          <ChevronRight size={40} className="hidden lg:block" />
        </div>

        {/* Step 3 */}
        <div className="flex-1 w-full bg-white border border-slate-200 rounded-2xl p-6 lg:p-8 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 w-24 h-24 bg-teal-50 rounded-bl-full -z-10"></div>
          <div className="w-14 h-14 rounded-full bg-teal-100 flex items-center justify-center text-teal-600 mb-5">
            <CheckCircle2 size={28} />
          </div>
          <h2 className="text-teal-600 font-black text-sm lg:text-base mb-1">STEP 3</h2>
          <h3 className="text-xl lg:text-2xl font-bold text-slate-900 mb-3">근거 문단 확인</h3>
          <p className="text-[14px] lg:text-[15px] text-slate-600 leading-relaxed break-keep">
            답변 아래의 '근거 문단 보기' 버튼을 눌러 AI가 참고한 실제 원문 공고의 위치와 내용을 직접 확인하여 신뢰도를 높이세요.
          </p>
        </div>

      </div>

      <div className="mt-10 flex justify-center">
        <button 
          onClick={() => { go("list"); showToast("공고 목록으로 이동합니다."); }}
          className="flex items-center gap-2 bg-blue-600 text-white font-bold text-lg px-8 py-4 rounded-xl hover:bg-blue-700 hover:-translate-y-1 transition-all shadow-lg"
        >
          지금 바로 공고 찾아보기 <ArrowRight size={20} />
        </button>
      </div>
    </UserLayout>
  );
}
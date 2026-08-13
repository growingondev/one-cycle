import { useState } from "react";
import { Search, BookOpen } from "lucide-react";
import { UserLayout } from "../layout/UserLayout";
import { Icon } from "../common/Icons";

const glossaryDummyData = [
  { category: "청약/자격", term: "무주택 세대구성원", desc: "세대원 전원이 주택을 소유하고 있지 않은 세대의 구성원을 의미합니다. 청약의 가장 기본이 되는 필수 조건입니다." },
  { category: "주택/유형", term: "신혼희망타운", desc: "육아, 보육을 비롯한 신혼부부의 수요를 반영하여 건설하고 전량 신혼부부 및 예비신혼부부 등에게 공급하는 특화형 공공주택입니다." },
  { category: "소득/자산", term: "소득 분위", desc: "통계청에서 발표하는 소득 10분위 자료를 바탕으로, 가구당 월평균 소득을 기준으로 나눈 구간입니다. 130% 이하 등의 기준에 사용됩니다." },
  { category: "주택/유형", term: "공공분양", desc: "국가, 지자체, LH 등이 국민주택기금을 지원받아 건설하여 공급하는 전용면적 85㎡ 이하의 주택으로, 내 집 마련을 위한 분양 주택입니다." },
  { category: "청약/자격", term: "예비신혼부부", desc: "공고일 현재 혼인 중이 아니나, 입주 전까지 혼인사실을 증명할 수 있는 사람을 말합니다." },
  { category: "주택/유형", term: "행복주택", desc: "대학생, 청년, 신혼부부 등을 위해 직장과 학교가 가까운 곳이나 대중교통이 편리한 곳에 짓는 임대료가 저렴한 공공임대주택입니다." },
  { category: "소득/자산", term: "도시근로자 가구당 월평균소득", desc: "전년도 도시근로자 가구의 월평균 소득을 말하며, 가구원수별로 금액이 다릅니다. 청약 자격의 주요 기준이 됩니다." },
  { category: "기타", term: "선착순 동호지정", desc: "정해진 기간 내에 미분양된 잔여 세대에 대해, 먼저 오는 순서대로 원하는 동과 호수를 지정하여 계약하는 방식입니다." },
];

const categories = ["전체", "청약/자격", "주택/유형", "소득/자산", "기타"];

export function GlossaryScreen({ go, showToast }: { go: (s: any) => void; showToast: (m: string) => void; }) {
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("전체");

  // 검색어와 선택된 탭 조건에 맞게 데이터 필터링
  const filteredData = glossaryDummyData.filter(item => {
    const matchCategory = activeTab === "전체" || item.category === activeTab;
    const matchQuery = item.term.includes(query) || item.desc.includes(query);
    return matchCategory && matchQuery;
  });

  return (
    <UserLayout screen="glossary" go={go} showToast={showToast}>
      <button className="flex items-center gap-1.5 text-sm font-bold text-slate-600 hover:text-slate-900 mb-4 lg:mb-6 transition-colors" onClick={() => go("list")}>
        <Icon name="back" size={16} /> 목록으로 돌아가기
      </button>

      <section className="mb-6 lg:mb-8 flex flex-col lg:flex-row lg:items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] lg:text-[30px] font-extrabold text-slate-900 tracking-tight leading-tight flex items-center gap-3">
            <BookOpen className="text-blue-600" size={32} /> 청약 용어 사전
          </h1>
          <p className="text-sm lg:text-base text-slate-500 mt-2">어렵고 복잡한 청약 관련 용어를 쉽게 찾아보세요.</p>
        </div>

        {/* 우측 검색바 */}
        <div className="flex border border-slate-300 rounded-lg overflow-hidden h-12 w-full lg:w-[300px] bg-white focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all shadow-sm">
          <div className="flex items-center pl-4 text-slate-400">
            <Search size={18} />
          </div>
          <input
            className="flex-1 border-0 px-3 outline-none text-sm w-full"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="어떤 용어가 궁금하신가요?"
          />
        </div>
      </section>

      {/* 작동하는 카테고리 탭 (인터랙션 요소) */}
      <div className="flex overflow-x-auto gap-2 mb-6 pb-2 scrollbar-hide">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => { setActiveTab(cat); showToast(`'${cat}' 카테고리를 선택했습니다.`); }}
            className={`whitespace-nowrap px-5 py-2.5 rounded-full text-[14px] font-bold transition-all border ${
              activeTab === cat 
                ? "bg-slate-800 text-white border-slate-800 shadow-md" 
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-300"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 용어 카드 리스트 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 lg:gap-5">
        {filteredData.map((item, i) => (
          <div key={i} className="bg-white border border-slate-200 rounded-xl p-5 lg:p-6 shadow-sm hover:shadow-md hover:border-blue-300 transition-all group cursor-pointer" onClick={() => showToast(`'${item.term}' 용어를 클릭했습니다.`)}>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-[11px] font-black bg-slate-100 text-slate-500 px-2 py-1 rounded-md tracking-tight">
                {item.category}
              </span>
              <h3 className="text-[17px] font-extrabold text-blue-700 group-hover:text-blue-800 transition-colors">{item.term}</h3>
            </div>
            <p className="text-[14px] text-slate-600 leading-relaxed break-keep">{item.desc}</p>
          </div>
        ))}
        
        {/* 검색 결과 없음 처리 */}
        {filteredData.length === 0 && (
          <div className="col-span-full py-20 text-center bg-slate-50 rounded-xl border border-slate-200 border-dashed">
            <div className="text-slate-400 mb-3 flex justify-center"><Search size={40} /></div>
            <h3 className="text-lg font-bold text-slate-700 mb-1">검색된 용어가 없습니다</h3>
            <p className="text-sm text-slate-500">다른 검색어를 입력하거나 카테고리를 변경해 보세요.</p>
          </div>
        )}
      </div>
    </UserLayout>
  );
}
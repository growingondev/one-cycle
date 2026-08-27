import { useState, useEffect } from "react";
import { Menu, X, ChevronRight } from "lucide-react";
import { Logo, Icon } from "../common/Icons";

type Screen = "list" | "detail" | "guide" | "glossary" | "admin-notices" | "admin-docs" | "admin-errors";

function openLH() {
  window.open("https://apply.lh.or.kr/", "_blank", "noopener,noreferrer");
}

export function UserLayout({ screen, go, showToast, children }: { screen: Screen; go: (s: Screen) => void; showToast: (m: string) => void; children: React.ReactNode; }) {
  const active = screen === "detail" ? "list" : screen;
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  useEffect(() => setMobileMenuOpen(false), [screen]);

  return (
    <div className="flex w-full min-h-screen bg-slate-50 lg:bg-white text-slate-800">
      
      {/* 1. 데스크톱 좌측 사이드바 */}
      <aside className="hidden lg:flex fixed left-0 top-0 bottom-0 w-[270px] xl:w-[280px] border-r border-slate-200 bg-white flex-col z-10 px-4 py-10">
        <Logo />
        <nav className="mt-8 flex flex-col gap-3">
          {[
            { id: "list", icon: "list", label: "공고 목록" },
            { id: "guide", icon: "guide", label: "이용 안내" }
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => go(item.id as Screen)}
              className={`w-full h-14 flex items-center gap-4 px-5 rounded-lg text-base font-semibold transition-colors ${
                active === item.id ? "bg-blue-50 text-blue-600" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <Icon name={item.icon} size={22} /> {item.label}
            </button>
          ))}
        </nav>
        
        {/* 사이드바 하단 안내 박스 */}
        <div className="mt-auto border border-slate-200 rounded-xl p-5 bg-slate-50">
          <b className="text-[18px] text-slate-800">안내</b>
          <p className="text-sm text-slate-700 mt-3 leading-relaxed">
            LH 청약플러스의 임대주택 공고를 AI가 쉽게 이해할 수 있도록 도와드립니다.
          </p>
          <button onClick={() => { showToast("새 창을 엽니다."); openLH(); }} className="w-full mt-3 bg-blue-100 text-blue-700 font-bold text-sm py-3 rounded-lg flex items-center justify-center gap-2 hover:bg-blue-200 transition-colors">
            LH 청약플러스 바로가기 <Icon name="ext" size={25} />
          </button>
        </div>
      </aside>

      {/* 2. 모바일 상단 헤더 */}
      <header className="lg:hidden fixed top-0 w-full h-[70px] bg-white border-b border-slate-200 flex items-center justify-between px-5 z-50">
        <Logo />
        <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="p-2 text-slate-800">
          {mobileMenuOpen ? <X size={28} /> : <Menu size={28} />}
        </button>
      </header>

      {/* 3. 우측 메인 콘텐츠 영역 (비율 조정 적용) */}
      <main className="w-full lg:ml-[270px] xl:ml-[280px] pt-[90px] lg:pt-8 px-5 lg:px-10 pb-24 lg:pb-12 min-h-screen">
        {children}
      </main>

      {/* 4. 모바일 하단 네비게이션 */}
      <nav className="lg:hidden fixed bottom-0 w-full h-[70px] bg-white border-t border-slate-200 shadow-[0_-4px_14px_rgba(0,0,0,0.03)] grid grid-cols-2 z-50">
        {[
          { id: "list", icon: "list", label: "공고 목록" },
          { id: "guide", icon: "guide", label: "이용 안내" }
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => go(item.id as Screen)}
            className={`flex flex-col items-center justify-center gap-1 text-[11px] font-bold ${active === item.id ? "text-blue-600" : "text-slate-500"}`}
          >
            <Icon name={item.icon} size={24} /> {item.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
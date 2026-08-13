import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
// 하단에서 페이지 번호를 이동하는 공통 부품입니다.
export function Pagination({
  pages,
  page,
  onChange,
}: {
  pages: number;
  page: number;
  onChange: (p: number) => void;
}) {
  const set = (p: number) => onChange(Math.max(1, Math.min(pages, p)));

  return (
    <div className="flex items-center justify-center gap-1.5 lg:gap-2.5 h-16 lg:h-20 mt-2">
      <button aria-label="첫 페이지" onClick={() => set(1)} className="w-8 h-8 lg:w-9 lg:h-9 flex items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 transition-colors">
        <ChevronsLeft size={18} />
      </button>
      <button aria-label="이전 페이지" onClick={() => set(page - 1)} className="w-8 h-8 lg:w-9 lg:h-9 flex items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 transition-colors">
        <ChevronLeft size={18} />
      </button>
      
      {Array.from({ length: pages }, (_, i) => (
        <button
          key={i}
          onClick={() => set(i + 1)}
          className={`w-8 h-8 lg:w-9 lg:h-9 flex items-center justify-center rounded-md text-[13px] lg:text-sm transition-colors ${
            page === i + 1
              ? "bg-blue-600 text-white font-bold"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          {i + 1}
        </button>
      ))}
      
      <button aria-label="다음 페이지" onClick={() => set(page + 1)} className="w-8 h-8 lg:w-9 lg:h-9 flex items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 transition-colors">
        <ChevronRight size={18} />
      </button>
      <button aria-label="마지막 페이지" onClick={() => set(pages)} className="w-8 h-8 lg:w-9 lg:h-9 flex items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 transition-colors">
        <ChevronsRight size={18} />
      </button>
    </div>
  );
}
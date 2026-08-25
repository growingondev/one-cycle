import { ReactNode } from "react";

interface GlossaryTooltipProps {
  term: string;
  definition: string;
  children: ReactNode;
}

export function GlossaryTooltip({ term, definition, children }: GlossaryTooltipProps) {
  return (
    <span className="relative inline-block group cursor-help">
      {/* 화면에 표시될 강조된 용어 (파란색 물결 밑줄) */}
      <span className="text-blue-700 font-bold underline decoration-blue-300 decoration-wavy underline-offset-4 group-hover:text-blue-800 transition-colors">
        {children}
      </span>

      {/* 마우스 호버 시 나타날 툴팁 */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-max max-w-[240px] hidden group-hover:block z-50 animate-fadeIn pointer-events-none">
        <div className="bg-slate-800 text-white text-[13px] rounded-lg p-3 shadow-lg">
          <strong className="block text-blue-300 mb-1 text-[14px]">{term}</strong>
          <span className="leading-relaxed break-keep">{definition}</span>
        </div>
        {/* 말풍선 아래쪽 꼬리 */}
        <div className="absolute top-full left-1/2 -translate-x-1/2 border-[6px] border-transparent border-t-slate-800"></div>
      </div>
    </span>
  );
}
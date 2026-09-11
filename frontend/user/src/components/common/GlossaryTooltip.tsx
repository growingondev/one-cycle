import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";

export function GlossaryTooltip({
  children,
  term,
  definition,
}: {
  children: React.ReactNode;
  term: string;
  definition: string;
}) {
  const [show, setShow] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLSpanElement>(null);

  const handleMouseEnter = () => {
    if (triggerRef.current) {
      // 1. 단어의 현재 화면상 위치(좌표)를 계산합니다.
      const rect = triggerRef.current.getBoundingClientRect();
      setCoords({
        top: rect.top - 10, // 단어 위쪽으로 띄우기 (필요에 따라 조절)
        left: rect.left + rect.width / 2, // 단어의 가운데 정렬
      });
      setShow(true);
    }
  };

  const handleMouseLeave = () => {
    setShow(false);
  };

  // 2. 화면 스크롤 시 툴팁 위치가 엇나가는 것을 방지하기 위해 닫아줍니다.
  useEffect(() => {
    const handleScroll = () => setShow(false);
    if (show) {
      window.addEventListener("scroll", handleScroll, true);
    }
    return () => window.removeEventListener("scroll", handleScroll, true);
  }, [show]);

  return (
    <>
      {/* 마우스를 올리는 단어 부분 */}
      <span
        ref={triggerRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className="text-blue-600 font-semibold underline decoration-blue-300 underline-offset-4 cursor-help transition-colors hover:text-blue-800"
      >
        {children}
      </span>

      {/* 💡 마법의 Portal! 채팅창(div)을 벗어나 HTML <body> 태그에 직접 툴팁을 그립니다 */}
      {show &&
        createPortal(
          <div
            className="fixed z-[9999] w-64 p-3 bg-slate-900 text-white text-[13px] leading-relaxed rounded-xl shadow-2xl transform -translate-x-1/2 -translate-y-full pointer-events-none"
            style={{
              top: `${coords.top}px`,
              left: `${coords.left}px`,
            }}
          >
            {/* 말풍선 꼬리표 (아래쪽 뾰족한 부분) */}
            <div className="absolute -bottom-1.5 left-1/2 transform -translate-x-1/2 w-3 h-3 bg-slate-900 rotate-45"></div>
            
            <strong className="block text-blue-300 font-bold mb-1 border-b border-slate-700 pb-1">
              {term}
            </strong>
            {definition}
          </div>,
          document.body
        )}
    </>
  );
}
import { useState, useEffect } from "react";
import { Icon } from "./Icons";
// 목록에서 '지역'이나 '상태'를 필터링할 때 사용하는 공통 드롭다운(선택창) 부품입니다.
export function DropdownSelect({
  values,
  value,
  onChange,
  className = "",
  label,
}: {
  values: string[];
  value: string;
  onChange: (v: string) => void;
  className?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const id = window.setTimeout(() => document.addEventListener("click", close), 0);
    return () => {
      window.clearTimeout(id);
      document.removeEventListener("click", close);
    };
  }, [open]);

  return (
    <div className={`relative min-w-0 ${className}`} onClick={(e) => e.stopPropagation()}>
      <button
        className={`w-full h-11 lg:h-12 px-3.5 flex items-center justify-between gap-3 bg-white border rounded-lg text-sm font-medium whitespace-nowrap transition-all ${
          open ? "border-blue-500 ring-2 ring-blue-100" : "border-slate-300 hover:border-blue-400"
        } text-slate-800`}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {label && <span className="sr-only">{label}</span>}
        <span>{value}</span>
        <Icon name="down" size={16} />
      </button>
      
      {open && (
        <div className="absolute top-[calc(100%+6px)] left-0 right-0 z-50 bg-white border border-slate-200 rounded-lg shadow-lg p-1.5 max-h-[260px] overflow-auto" role="listbox">
          {values.map((v) => (
            <button
              key={v}
              role="option"
              aria-selected={v === value}
              className={`w-full min-h-[38px] px-2.5 py-2 flex items-center justify-between text-left text-sm rounded-md transition-colors ${
                v === value ? "bg-blue-50 text-blue-600 font-bold" : "text-slate-700 hover:bg-slate-50 hover:text-blue-600"
              }`}
              onClick={() => {
                onChange(v);
                setOpen(false);
              }}
            >
              {v}
              {v === value && <Icon name="check" size={15} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
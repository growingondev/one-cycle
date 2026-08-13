export function StatusPill({ children }: { children: string }) {
  const isRed = children.includes("실패") || children.includes("미해결");
  const isGreen = children === "공고중" || children === "수집완료" || children.includes("완료");
  const isBlue = children.includes("정정") || children.includes("예정");
  const isOrange = children.includes("처리중") || children.includes("수집중") || children.includes("해결 중");

  const colorClass = isRed
    ? "text-red-500 bg-red-50 border-red-200"
    : isGreen
    ? "text-emerald-600 bg-emerald-50 border-emerald-200"
    : isBlue
    ? "text-blue-600 bg-blue-50 border-blue-200"
    : isOrange
    ? "text-amber-500 bg-amber-50 border-amber-200"
    : "text-slate-500 bg-slate-100 border-slate-300";

  return (
    <span className={`inline-flex items-center justify-center whitespace-nowrap rounded-md border px-2.5 py-1 text-xs font-bold ${colorClass}`}>
      {children}
    </span>
  );
}
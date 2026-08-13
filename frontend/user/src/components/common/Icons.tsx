import {
  Search, ChevronDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  ArrowLeft, ExternalLink, Send, Info, List, BookOpen, FileText, UserRound,
  TriangleAlert, LogOut, ClipboardList, CalendarDays, House, CircleDollarSign,
  BadgeCheck, FileStack, Upload, Download, MoreVertical, Check, X, Settings,
  RefreshCw, Eye, Bot, MessageCircle, FileCheck2, Database, CircleHelp, Menu
} from "lucide-react";

export function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <div className="flex items-start gap-3 h-[62px] xl:h-[68px] px-2.5 border-b border-slate-100 lg:border-none">
      <div className={`relative font-black text-3xl tracking-tighter leading-none ${dark ? "text-blue-500" : "text-blue-600"}`}>
        <span>LH</span>
        <i className="absolute w-3 h-3 rounded-full bg-lime-500 -right-2 -top-1"></i>
      </div>
      <strong className={`text-xl xl:text-[21px] font-bold mt-1 ${dark ? "text-white" : "text-gray-900"}`}>
        공고 AI 도우미
      </strong>
    </div>
  );
}

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = { size, strokeWidth: 1.9, "aria-hidden": true as const };
  const map: Record<string, React.ReactNode> = {
    list: <List {...common} />, guide: <BookOpen {...common} />, glossary: <FileText {...common} />,
    admin: <UserRound {...common} />, error: <TriangleAlert {...common} />, doc: <ClipboardList {...common} />,
    logout: <LogOut {...common} />, search: <Search {...common} />, down: <ChevronDown {...common} />,
    back: <ArrowLeft {...common} />, ext: <ExternalLink {...common} />, send: <Send {...common} />,
    info: <Info {...common} />, upload: <Upload {...common} />, download: <Download {...common} />,
    more: <MoreVertical {...common} />, check: <Check {...common} />, close: <X {...common} />,
    settings: <Settings {...common} />, refresh: <RefreshCw {...common} />, eye: <Eye {...common} />,
    bot: <Bot {...common} />, chat: <MessageCircle {...common} />, filecheck: <FileCheck2 {...common} />,
    database: <Database {...common} />, help: <CircleHelp {...common} />
  };
  return <span className="inline-flex items-center justify-center">{map[name] ?? <CircleHelp {...common} />}</span>;
}
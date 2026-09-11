import { useState } from "react";
import { IntroScreen } from "./components/screens/IntroScreen";
import { ListScreen } from "./components/screens/ListScreen";
import { DetailScreen } from "./components/screens/DetailScreen";
import { GuideScreen } from "./components/screens/GuideScreen";
import { GlossaryScreen } from "./components/screens/GlossaryScreen";

type Screen = "intro" | "list" | "detail" | "guide" | "glossary" | "admin-notices" | "admin-docs" | "admin-errors";
type Toast = { message: string; id: number } | null;

// 💡 백엔드 서버 연동 주소
export const API_BASE_URL = "/api";

function useToast() {
  const [toast, setToast] = useState<Toast>(null);
  const showToast = (message: string) => {
    const id = Date.now();
    setToast({ message, id });
    window.setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 1800);
  };
  return { toast, showToast };
}

export default function App() {
  // 💡 앱 실행 시 첫 화면을 인트로(intro)로 유지합니다.
  const [screen, setScreen] = useState<Screen>("intro");
  
  const [selectedNotice, setSelectedNotice] = useState<any>(null);
  const { toast, showToast } = useToast();

  const go = (s: Screen, noticeData?: any) => {
    if (noticeData) {
      setSelectedNotice(noticeData);
    }
    setScreen(s);
    window.scrollTo(0, 0);
  };

  const ToastMessage = () => toast ? (
    <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[9999] bg-slate-800 text-white px-5 py-3 rounded-xl shadow-xl text-sm font-medium animate-[toastIn_0.2s_ease-out]">
      {toast.message}
    </div>
  ) : null;

  const renderScreen = () => {
    switch (screen) {
      case "intro":
        return <IntroScreen go={go} />;
      case "detail":
        return <DetailScreen go={go} showToast={showToast} notice={selectedNotice} />;
      case "guide":
        return <GuideScreen go={go} showToast={showToast} />;
      case "glossary":
        return <GlossaryScreen go={go} showToast={showToast} />;
      case "list":
      default:
        return <ListScreen go={go} showToast={showToast} />;
    }
  };

  return (
    <>
      {renderScreen()}
      <ToastMessage />
    </>
  );
}
import { useState, useEffect } from "react";
import {
  CalendarDays,
  House,
  BadgeCheck,
  CircleDollarSign,
  FileText,
  FileStack,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

import { UserLayout } from "../layout/UserLayout";
import { StatusPill } from "../common/StatusPill";
import { Icon } from "../common/Icons";
import { API_BASE_URL } from "../../config";


/* =========================
   공통 유틸
========================= */

function toDisplayText(
  value: unknown,
  fallback = "-"
): string {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return fallback;
  }

  if (typeof value === "string") {
    return value;
  }

  if (
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }

  if (Array.isArray(value)) {
    const values = value
      .map((item) => toDisplayText(item, ""))
      .filter(Boolean);

    return values.length > 0
      ? values.join(", ")
      : fallback;
  }

  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;

    const ignoredKeys = new Set([
      "source_titles",
      "source_section_ids",
      "source_chunk_ids",
      "source_ids",
    ]);

    const preferredKeys = [
      "text",
      "value",
      "content",
      "summary",
      "status",
      "note",
      "period",
      "start_date",
      "end_date",
      "start",
      "end",
      "date",
      "announcement_date",
      "contract_start",
      "location",
      "operating_hours",
      "break_time",
      "closed_days",
      "end_condition",
    ];

    const preferredValues = preferredKeys
      .filter(
        (key) =>
          key in obj &&
          !ignoredKeys.has(key) &&
          obj[key] !== null &&
          obj[key] !== undefined &&
          obj[key] !== ""
      )
      .map((key) => toDisplayText(obj[key], ""))
      .filter(Boolean);

    if (preferredValues.length > 0) {
      return preferredValues.join(" / ");
    }

    const remainingValues = Object.entries(obj)
      .filter(
        ([key, val]) =>
          !ignoredKeys.has(key) &&
          !key.startsWith("source_") &&
          val !== null &&
          val !== undefined &&
          val !== ""
      )
      .map(([, val]) => toDisplayText(val, ""))
      .filter(Boolean);

    return remainingValues.length > 0
      ? remainingValues.join(" / ")
      : fallback;
  }

  return fallback;
}


function compactCardValue(
  value: unknown,
  fallback: string,
  maxLength = 220
): string {
  const text = toDisplayText(
    value,
    fallback
  )
    .replace(/\s+/g, " ")
    .trim();

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength).trim()}…`;
}


/* =========================
   근거 모달
========================= */

function InfoModal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-[100] px-4"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-[560px] max-h-[85vh] overflow-auto rounded-2xl p-6 lg:p-8 relative shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="absolute right-5 top-5 text-slate-400 hover:text-slate-600 text-2xl"
          onClick={onClose}
        >
          ×
        </button>

        <h2 className="text-xl font-bold text-slate-900 mb-4">
          {title}
        </h2>

        {children}
      </div>
    </div>
  );
}


/* =========================
   핵심 정보 카드
========================= */

function SummaryCard({
  icon,
  title,
  rows,
}: {
  icon: string;
  title: string;
  rows: [string, string][];
}) {
  const iconNode =
    icon === "calendar" ? (
      <CalendarDays size={20} />
    ) : icon === "home" ? (
      <House size={20} />
    ) : icon === "eligibility" ? (
      <BadgeCheck size={20} />
    ) : icon === "price" ? (
      <CircleDollarSign size={20} />
    ) : (
      <FileText size={20} />
    );

  return (
    <div className="border border-slate-200 rounded-lg p-4 mb-3">
      <h3 className="flex items-center gap-2 text-blue-600 text-[16px] lg:text-[17px] font-bold mb-3">
        <span>{iconNode}</span>
        {title}
      </h3>

      {rows.map(([key, value], index) => (
        <div
          className="grid grid-cols-[80px_1fr] lg:grid-cols-[100px_1fr] gap-2 items-baseline text-[14px] lg:text-[15px] leading-relaxed mb-2 last:mb-0"
          key={`${key}-${index}`}
        >
          <b className="text-slate-500 font-semibold">
            {key}
          </b>

          <span className="text-slate-900 font-medium text-[14px] lg:text-[15px] break-words whitespace-pre-line">
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}


/* =========================
   타입
========================= */

type EvidenceItem = {
  chunkId: string | number;
  sectionTitle?: string | null;
  content: string;
  score?: number | null;
};

type ChatMessage = {
  role: "user" | "ai";
  text: string;
  time: string;
  evidence?: EvidenceItem[];
};


/* =========================
   상세 화면
========================= */

export function DetailScreen({
  go,
  showToast,
  notice,
}: {
  go: (s: any) => void;
  showToast: (m: string) => void;
  notice?: any;
}) {
  const [evidence, setEvidence] = useState<EvidenceItem[] | null>(null);
  const [input, setInput] = useState("");
  const [isSummaryOpen, setIsSummaryOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentNotice, setCurrentNotice] = useState<any>(notice || null);

  // 💡 제출서류 근거 확인 토글을 위한 상태
  const [showDocsEvidence, setShowDocsEvidence] = useState(false);

  /* =========================
     목록에서 전달받은 공고
  ========================= */

  useEffect(() => {
    if (notice) {
      setCurrentNotice(notice);
    }
  }, [notice]);


  /* =========================
     상세 공고 API
  ========================= */

  useEffect(() => {
    if (!notice?.id) return;

    fetch(
      `${API_BASE_URL}/announcements/${notice.id}`
    )
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text();
          throw new Error(
            `상세 공고 서버 오류: ${res.status}\n${text}`
          );
        }
        return res.json();
      })
      .then((data) => {
        console.log("상세 공고 API 응답:", data);
        if (data) {
          setCurrentNotice(data);
        }
      })
      .catch((err) => {
        console.error("상세 데이터 로딩 실패:", err);
        showToast("공고 상세 정보를 불러오지 못했습니다.");
      });
  }, [notice?.id]);


  /* =========================
     채팅
  ========================= */

  const send = async () => {
    if (!input.trim() || !currentNotice) {
      showToast("질문을 입력해 주세요.");
      return;
    }

    const now = new Date().toLocaleTimeString(
      "ko-KR",
      { hour: "2-digit", minute: "2-digit", hour12: false }
    );

    const userMsg = input.trim();

    setMessages((messages) => [
      ...messages,
      { role: "user", text: userMsg, time: now },
    ]);

    setInput("");
    showToast("AI가 답변을 생성하고 있습니다.");

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          announcementId: currentNotice.id,
          question: userMsg,
        }),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`채팅 API 오류: ${response.status}\n${text}`);
      }

      const data = await response.json();
      console.log("채팅 API 응답:", data);

      setMessages((messages) => [
        ...messages,
        {
          role: "ai",
          text: typeof data.answer === "string" ? data.answer : toDisplayText(data.answer, "답변을 생성하지 못했습니다."),
          time: now,
          evidence: Array.isArray(data.evidence) ? data.evidence : [],
        },
      ]);
    } catch (err) {
      console.error("채팅 API 요청 실패:", err);
      setMessages((messages) => [
        ...messages,
        {
          role: "ai",
          text: "서버 통신에 실패했습니다. 백엔드 챗봇 서버가 연결되어 있는지 확인해주세요.",
          time: now,
        },
      ]);
    }
  };


  /* =========================
     로딩
  ========================= */

  if (!currentNotice) {
    return (
      <UserLayout screen="detail" go={go} showToast={showToast}>
        <div className="flex flex-col items-center justify-center py-20">
          <p className="text-slate-500 mb-4">공고 데이터를 불러오는 중이거나 선택된 공고가 없습니다.</p>
          <button onClick={() => go("list")} className="px-4 py-2 bg-blue-600 text-white rounded-lg font-bold">
            목록으로 돌아가기
          </button>
        </div>
      </UserLayout>
    );
  }


  /* =========================
     백엔드 JSON → 화면 데이터
  ========================= */

  const keyInformation = currentNotice.keyInformation ?? {};
  const applicationPeriod = keyInformation.applicationPeriod ?? keyInformation.application_period ?? {};
  const supplyInformation = keyInformation.supplyInformation ?? keyInformation.supply_information ?? {};
  const eligibility = keyInformation.eligibility ?? {};
  const incomeAssetCriteria = keyInformation.incomeAssetCriteria ?? keyInformation.income_asset_criteria ?? {};
  const requiredDocuments = keyInformation.requiredDocuments ?? keyInformation.required_documents ?? {};
  const winnerAnnouncement = keyInformation.winnerAnnouncement ?? keyInformation.winner_announcement ?? {};

  // 데이터 보정 (크롤러의 새 데이터 적용)
  const displayAnnouncementDate = toDisplayText(
    currentNotice.post_date ??
    currentNotice.announcementDate ??
    currentNotice.date ??
    applicationPeriod.announcement_date ??
    applicationPeriod.announcementDate,
    "-"
  );

  const rawPublicationStatus = currentNotice.publication_status ?? currentNotice.publicationStatus ?? currentNotice.status;
  const displayPublicationStatus = rawPublicationStatus === "fixture" ? "상태 미확인" : toDisplayText(rawPublicationStatus, "상태 미확인");
  const displayLocation = toDisplayText(currentNotice.region ?? supplyInformation.block, "-");


  /* =========================
     신청 일정
  ========================= */
  const applicationPeriodDisplay =
    applicationPeriod.start && applicationPeriod.end
      ? `${applicationPeriod.start} ~ ${applicationPeriod.end}`
      : compactCardValue(
          applicationPeriod.summary,
          "공고문 참조",
          120
        );

  const scheduleData: [string, string][] = [
    [
      "게시일",
      displayAnnouncementDate,
    ],
    [
      "신청 기간",
      applicationPeriodDisplay,
    ],
    [
      "마감일",
      compactCardValue(
        currentNotice.deadlineDate ??
          currentNotice.deadline_date ??
          applicationPeriod.end,
        "-",
        80
      ),
    ],
    [
      "발표일",
      compactCardValue(
        winnerAnnouncement.announcement_date,
        "공고문 참조",
        80
      ),
    ],
  ];


  const supplyData: [string, string][] = [
    [
      "공급 위치",
      compactCardValue(
        currentNotice.region ??
          supplyInformation.block,
        "공고문 참조",
        100
      ),
    ],
    [
      "공급 내용",
      compactCardValue(
        supplyInformation.summary,
        "공고문 공급 정보를 확인하세요.",
        230
      ),
    ],
  ];


  const eligibilityData: [string, string][] = [
    [
      "신청 자격",
      compactCardValue(
        eligibility.summary,
        "공고문 세부 자격 요건을 확인하세요.",
        230
      ),
    ],
    [
      "소득/자산",
      compactCardValue(
        incomeAssetCriteria.summary,
        "공고문 소득·자산 기준을 확인하세요.",
        230
      ),
    ],
  ];


  const extractedDocumentItems = Array.isArray(
    requiredDocuments.items
  )
    ? requiredDocuments.items
        .map((item: unknown) =>
          compactCardValue(
            item,
            "",
            100
          )
        )
        .filter(Boolean)
    : [];

  const docsData: string[] =
    extractedDocumentItems.length > 0
      ? extractedDocumentItems
      : [
          compactCardValue(
            requiredDocuments.summary,
            "공고문 세부 제출서류를 확인하세요.",
            180
          ),
        ];

  // Raw extracted text is shown only as evidence.
  const docsEvidenceText =
    requiredDocuments.evidence_text ??
    requiredDocuments.text ??
    "추출된 근거 정보가 없습니다."


  /* =========================
     화면
  ========================= */

  return (
    <UserLayout screen="detail" go={go} showToast={showToast}>
      <button className="flex items-center gap-1.5 text-[15px] lg:text-[16px] font-bold text-slate-600 hover:text-slate-900 mb-4 lg:mb-6 transition-colors" onClick={() => go("list")}>
        <Icon name="back" size={18} /> 목록으로 돌아가기
      </button>

      {/* 공고 제목 */}
      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-[26px] lg:text-[30px] font-extrabold text-slate-900 leading-tight tracking-tight mb-3 lg:mb-4">공고 상세 및 AI 질의응답</h1>

          <div className="flex flex-col lg:flex-row lg:items-center gap-3">
            <div className="flex-shrink-0 flex items-center gap-2">
              <StatusPill>{toDisplayText(displayPublicationStatus, "상태 미확인")}</StatusPill>
              {currentNotice.notice_type && (
                <span className="text-blue-600 bg-blue-50 px-2 py-1 rounded text-[13px] font-bold">{currentNotice.notice_type}</span>
              )}
            </div>
            <strong className="text-[17px] lg:text-[20px] text-slate-900 leading-snug">{toDisplayText(currentNotice.title, "공고명 없음")}</strong>
          </div>

          <div className="text-[13px] lg:text-[15px] text-slate-500 mt-3">
            <span className="mr-2">게시일</span> <span className="text-slate-800 font-medium mr-5">{toDisplayText(displayAnnouncementDate, "-")}</span>
            <span className="mr-2">공고 상태</span> <span className="text-slate-800 font-medium mr-5">{toDisplayText(displayPublicationStatus, "상태 미확인")}</span>
            {displayLocation !== "-" && (
              <><span className="mr-2">공급 위치</span><span className="text-slate-800 font-medium">{displayLocation}</span></>
            )}
          </div>
        </div>
      </div>

      {/* =====================
          메인 영역
      ====================== */}
      <div className="grid grid-cols-1 xl:grid-cols-[380px_minmax(0,1fr)] items-start gap-4 lg:gap-5">

        {/* =====================
            핵심정보
        ====================== */}
        <div className="min-w-0 bg-white border border-slate-200 rounded-xl p-4 lg:p-5 shadow-sm">
          <div className="flex items-center justify-between cursor-pointer xl:cursor-default" onClick={() => setIsSummaryOpen(!isSummaryOpen)}>
            <h2 className="text-[17px] lg:text-[19px] font-bold text-slate-900">핵심 정보 요약</h2>
            <button className="xl:hidden text-slate-500 hover:text-slate-800 p-1">{isSummaryOpen ? <ChevronUp size={22} /> : <ChevronDown size={22} />}</button>
          </div>

          <div className={`${isSummaryOpen ? "block mt-4" : "hidden"} xl:block xl:mt-4`}>
            <SummaryCard icon="calendar" title="신청 일정" rows={scheduleData} />
            <SummaryCard icon="home" title="공급 정보" rows={supplyData} />
            <SummaryCard icon="eligibility" title="신청 자격" rows={eligibilityData} />

            {/* 💡 제출서류 및 근거 확인 영역 (수정된 부분) */}
            <div className="relative border border-slate-200 rounded-lg p-4 mb-2">
              <div className="flex items-center justify-between mb-3">
                <h3 className="flex items-center gap-2 text-blue-600 text-[16px] lg:text-[17px] font-bold">
                  <FileStack size={20} /> 제출 서류
                </h3>
                <button
                  onClick={() => setShowDocsEvidence(!showDocsEvidence)}
                  className="flex items-center gap-1 text-[13px] bg-blue-50 text-blue-600 px-2 py-1 rounded hover:bg-blue-100 transition-colors"
                >
                  <FileText size={14} /> {showDocsEvidence ? "근거 닫기" : "근거 확인"}
                </button>
              </div>

              <ul className="text-[14px] lg:text-[15px] font-medium text-slate-800 leading-relaxed pl-5 list-disc mb-4 break-keep">
                {docsData.map((doc, index) => <li key={index}>{doc}</li>)}
              </ul>

              {/* 버튼 클릭 시 노출되는 AI 원본 텍스트 */}
              {showDocsEvidence && (
                <div className="bg-amber-50 border border-amber-200 p-3 rounded-lg text-[13px] text-slate-700 leading-relaxed whitespace-pre-wrap break-words mt-4 max-h-72 overflow-auto">
                  <b className="text-amber-700 block mb-1">🔍 AI 문서 추출 원본</b>
                  {toDisplayText(docsEvidenceText, "")}
                </div>
              )}
            </div>

            <p className="text-[12px] text-slate-400 mt-3 break-keep">※ 핵심 정보는 공고문을 AI가 분석하여 추출한 내용으로, 실제 공고문을 원본으로 확인하세요.</p>
          </div>
        </div>

        {/* =====================
            AI 채팅
        ====================== */}
        <div className="min-w-0 bg-white border border-slate-200 rounded-xl p-4 lg:p-5 shadow-sm flex flex-col h-[600px] lg:h-[700px]">
          <h2 className="text-[17px] lg:text-[19px] font-bold text-slate-900 mb-1">AI에게 무엇이든 물어보세요</h2>
          <p className="text-[13px] lg:text-[14px] text-slate-500 mb-4">공고에 대해 궁금한 내용을 질문하면 AI가 답변해 드립니다.</p>

          <div className="flex-1 overflow-auto px-2 py-4 bg-slate-50/50 rounded-lg border border-slate-100">
            {messages.length === 0 && <div className="text-center text-slate-400 py-10 text-sm">질문을 입력하면 이곳에 AI 답변이 표시됩니다.</div>}

            {messages.map((message, index) => message.role === "user" ? (
              <div key={index} className="flex flex-col items-end mb-5">
                <div className="max-w-[80%] lg:max-w-[65%] bg-blue-600 text-white text-[14px] lg:text-[15px] leading-relaxed px-4 py-3 rounded-2xl rounded-br-sm shadow-sm whitespace-pre-wrap break-keep">{message.text}</div>
                <small className="text-[11px] text-slate-400 mt-1.5">{message.time}</small>
              </div>
            ) : (
              <div key={index} className="flex items-start gap-2.5 mb-5">
                <div className="w-8 h-8 rounded-full border-2 border-blue-500 text-blue-600 flex items-center justify-center text-[12px] font-black flex-shrink-0 bg-white shadow-sm">AI</div>
                <div className="flex flex-col items-start max-w-[80%] lg:max-w-[70%]">
                  <div className="bg-white border border-slate-200 text-slate-800 text-[14px] lg:text-[15px] leading-relaxed px-4 py-3 rounded-2xl rounded-tl-sm shadow-sm whitespace-pre-wrap break-keep">
                    {message.text}
                    {message.evidence && message.evidence.length > 0 && (
                      <button onClick={() => setEvidence(message.evidence ?? [])} className="block mt-3 bg-blue-50 text-blue-600 text-[13px] font-bold px-3 py-1.5 rounded-md hover:bg-blue-100 transition-colors">근거 문단 보기</button>
                    )}
                  </div>
                  <small className="text-[11px] text-slate-400 mt-1.5">{message.time}</small>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4">
            <div className="flex h-12 lg:h-14 border border-slate-300 rounded-lg overflow-hidden focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all shadow-sm">
              <input className="flex-1 border-0 px-4 outline-none text-[14px] lg:text-[15px]" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} placeholder="궁금한 내용을 입력하세요." />
              <button onClick={send} className="w-[50px] lg:w-[60px] bg-white text-blue-600 hover:bg-blue-50 flex items-center justify-center transition-colors"><Icon name="send" size={20} /></button>
            </div>
          </div>
        </div>
      </div>

      {/* =====================
          근거 모달
      ====================== */}
      {evidence && (
        <InfoModal title="답변 근거" onClose={() => setEvidence(null)}>
          <p className="text-slate-500 text-sm mb-4">AI 답변에 실제 사용된 원문 문단입니다.</p>
          <div className="space-y-4">
            {evidence.map((item, index) => (
              <div key={`${item.chunkId}-${index}`} className="border border-slate-200 rounded-lg p-4">
                <div className="text-[13px] text-slate-500 mb-2"><b className="text-slate-700 mr-2">근거 {index + 1}</b>{toDisplayText(item.sectionTitle, "문서 위치 미상")}</div>
                <div className="text-[14px] text-slate-800 leading-relaxed whitespace-pre-wrap break-keep">{toDisplayText(item.content, "근거 내용이 없습니다.")}</div>
                {typeof item.score === "number" && <div className="text-[11px] text-slate-400 mt-2">score: {item.score.toFixed(4)}</div>}
              </div>
            ))}
          </div>
          <div className="flex justify-end mt-6"><button onClick={() => setEvidence(null)} className="bg-blue-600 text-white font-bold px-5 py-2.5 rounded-lg hover:bg-blue-700 transition-colors">닫기</button></div>
        </InfoModal>
      )}
    </UserLayout>
  );
}
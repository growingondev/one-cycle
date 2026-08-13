import { useState, useMemo, useEffect } from "react";
import { ChevronRight } from "lucide-react";
import { UserLayout } from "../layout/UserLayout";
import { DropdownSelect } from "../common/DropdownSelect";
import { Pagination } from "../common/Pagination";
import { StatusPill } from "../common/StatusPill";
import { Icon } from "../common/Icons";
import { API_BASE_URL } from "../../config";

type Screen =
  | "list"
  | "detail"
  | "guide"
  | "glossary"
  | "admin-notices"
  | "admin-docs"
  | "admin-errors";

type Announcement = {
  id: number;
  title: string;
  region: string | null;
  announcementDate: string | null;
  publicationStatus: string | null;
  // 새로 추가된 크롤링 데이터 타입
  notice_number?: string;
  notice_type?: string;
  post_date?: string;
  deadline_date?: string;
  publication_status?: string | null;
};

function formatAnnouncementTitle(title: string | null | undefined) {
  return (title ?? "-")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function formatPublicationStatus(
  status: string | null | undefined
) {
  if (!status || status === "fixture") {
    return "상태 미확인";
  }
  return status;
}

export function ListScreen({
  go,
  showToast,
}: {
  go: (s: Screen, notice?: any) => void;
  showToast: (m: string) => void;
}) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [query, setQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [region, setRegion] = useState("지역 전체");
  const [status, setStatus] = useState("공고 상태 전체");
  const [sort, setSort] = useState("최신순");
  const [page, setPage] = useState(1);

  const pageSize = 6;

  useEffect(() => {
    fetch(`${API_BASE_URL}/announcements`)
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text();
          throw new Error(
            `서버 응답 오류: ${res.status} ${res.statusText}\n${text}`
          );
        }
        return res.json();
      })
      .then((data) => {
        console.log("공고 목록 API 응답:", data);

        if (Array.isArray(data?.items)) {
          setAnnouncements(data.items);

          if (data.items.length > 0) {
            showToast("백엔드 연동 성공: 데이터를 불러왔습니다.");
          } else {
            showToast("백엔드와 연결되었으나 데이터가 없습니다.");
          }
          return;
        }

        console.error("예상하지 못한 공고 목록 응답 형식:", data);
        setAnnouncements([]);
        showToast("백엔드 응답 형식이 올바르지 않습니다.");
      })
      .catch((err) => {
        console.error("Backend fetch error:", err);
        setAnnouncements([]);
        showToast(
          "백엔드 연결 실패. 서버가 켜져있는지, 주소가 맞는지 확인하세요."
        );
      });
  }, [showToast]);

  const filtered = useMemo(() => {
    return announcements
      .filter((a) => {
        const title = formatAnnouncementTitle(a.title);
        const announcementRegion = a.region ?? "";
        const announcementStatus = formatPublicationStatus(a.publication_status || a.publicationStatus);

        const matchesSearch =
          !searchQuery ||
          title.toLowerCase().includes(searchQuery.toLowerCase());

        const matchesRegion =
          region === "지역 전체" || announcementRegion === region;

        const matchesStatus =
          status === "공고 상태 전체" ||
          announcementStatus === status;

        return matchesSearch && matchesRegion && matchesStatus;
      })
      .sort((a, b) => {
        // 에러 수정: 괄호를 씌워서 우선순위를 명확히 함
        const aDate = (a.post_date || a.announcementDate) ?? "";
        const bDate = (b.post_date || b.announcementDate) ?? "";

        return sort === "최신순"
          ? bDate.localeCompare(aDate)
          : aDate.localeCompare(bDate);
      });
  }, [announcements, searchQuery, region, status, sort]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));

  const visible = filtered.slice(
    (page - 1) * pageSize,
    page * pageSize
  );

  useEffect(() => {
    if (page > pages) {
      setPage(pages);
    }
  }, [pages, page]);

  const search = () => {
    setSearchQuery(query.trim());
    setPage(1);

    showToast(
      query.trim()
        ? `'${query.trim()}' 검색 결과를 반영했습니다.`
        : "전체 공고를 표시합니다."
    );
  };

  const goToDetail = (noticeItem: Announcement) => {
    go("detail", noticeItem);
  };

  return (
    <UserLayout
      screen="list"
      go={go}
      showToast={showToast}
    >
      <div className="mb-6 lg:mb-8">
        <h1 className="text-2xl lg:text-3xl font-black text-slate-900 mb-2">
          분양주택 공고 목록
        </h1>

        <p className="text-sm lg:text-base text-slate-500">
          LH 청약플러스의 분양주택 공고를 제공합니다.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 lg:p-6 shadow-sm mb-6 lg:mb-8">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(400px,1fr)_140px_160px_120px] gap-3 lg:gap-4 items-center">
          <label className="flex border border-slate-300 rounded-lg overflow-hidden h-11 lg:h-12 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
            <input
              className="flex-1 border-0 px-4 outline-none text-sm lg:text-base w-full"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  search();
                }
              }}
              placeholder="공고명 검색"
            />

            <button
              onClick={search}
              className="w-[60px] lg:w-[72px] bg-blue-600 text-white font-bold hover:bg-blue-700 transition-colors"
            >
              검색
            </button>
          </label>

          <DropdownSelect
            label="지역 필터"
            values={[
              "지역 전체",
              "전국",
              "서울특별시",
              "울산광역시",
              "충청북도",
              "충청남도",
              "경기도",
              "경상남도",
              "부산광역시"
            ]}
            value={region}
            onChange={(v) => {
              setRegion(v);
              setPage(1);
            }}
          />

          <DropdownSelect
            label="공고 상태 필터"
            values={[
              "공고 상태 전체",
              "공고중",
              "정정공고중",
              "접수중",
              "마감",
              "상태 미확인",
            ]}
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />

          <DropdownSelect
            label="정렬"
            className="lg:ml-auto w-full"
            values={["최신순", "오래된순"]}
            value={sort}
            onChange={(v) => {
              setSort(v);
              setPage(1);
            }}
          />
        </div>

        <p className="flex items-center gap-2 text-xs lg:text-[13px] text-slate-500 mt-5">
          <Icon name="info" size={14} />
          총 {filtered.length}건의 공고가 있습니다.
        </p>
      </div>

      <div className="hidden lg:block bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="grid grid-cols-[60px_100px_minmax(300px,1fr)_100px_110px_110px_100px_40px] items-center h-[52px] bg-slate-50 border-b border-slate-200 text-[14px] font-bold text-slate-700 px-2 text-center">
          <div>번호</div>
          <div>유형</div>
          <div className="text-left px-4">공고명</div>
          <div>지역</div>
          <div>게시일</div>
          <div>마감일</div>
          <div>상태</div>
          <div></div>
        </div>

        {visible.map((a) => (
          <button
            key={a.id}
            onClick={() => goToDetail(a)}
            className="w-full grid grid-cols-[60px_100px_minmax(300px,1fr)_100px_110px_110px_100px_40px] items-center min-h-[68px] border-b border-slate-100 bg-white hover:bg-blue-50/50 text-[13px] text-slate-700 transition-colors px-2 text-center"
          >
            <div className="font-bold text-[14px] text-slate-500">
              {a.notice_number || a.id}
            </div>

            <div className="text-blue-600 font-semibold">
              {a.notice_type || "유형없음"}
            </div>

            <div className="px-4 font-semibold text-[15px] text-slate-900 leading-relaxed text-left break-keep">
              {formatAnnouncementTitle(a.title)}
            </div>

            <div>
              {a.region ?? "-"}
            </div>

            {/* 에러 수정: 괄호를 씌워서 처리 */}
            <div>
              {(a.post_date || a.announcementDate) ?? "-"}
            </div>
            
            <div>
              {a.deadline_date ?? "-"}
            </div>

            <div>
              <StatusPill>
                {formatPublicationStatus(a.publication_status || a.publicationStatus)}
              </StatusPill>
            </div>

            <div className="text-slate-400 text-xl">›</div>
          </button>
        ))}

        {visible.length === 0 && (
          <div className="py-12 text-center text-slate-500">
            조건에 맞는 공고가 없습니다.
          </div>
        )}

        <Pagination
          pages={pages}
          page={page}
          onChange={(p) => {
            setPage(p);

            window.scrollTo({
              top: 0,
              behavior: "smooth",
            });

            showToast(`${p}페이지로 이동했습니다.`);
          }}
        />
      </div>

      <div className="flex flex-col gap-3 lg:hidden">
        {visible.map((a) => (
          <button
            key={`mobile-${a.id}`}
            onClick={() => goToDetail(a)}
            className="w-full bg-white border border-slate-200 rounded-xl p-4 text-left shadow-sm flex items-start gap-3 active:bg-slate-50 transition-colors"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-blue-600 bg-blue-50 px-2 py-0.5 rounded text-[11px] font-bold">{a.notice_type || "유형없음"}</span>
                <StatusPill>
                  {formatPublicationStatus(a.publication_status || a.publicationStatus)}
                </StatusPill>
              </div>

              <strong className="block text-[15px] font-extrabold text-slate-900 leading-snug mb-2.5 break-keep">
                {formatAnnouncementTitle(a.title)}
              </strong>

              <div className="flex flex-col gap-1 text-[12px] text-slate-500">
                <span>📍 {a.region ?? "-"}</span>
                {/* 에러 수정: 괄호를 씌워서 처리 */}
                <span>📅 {(a.post_date || a.announcementDate) ?? "-"} ~ {a.deadline_date ?? "-"}</span>
              </div>
            </div>

            <ChevronRight
              className="text-slate-400 self-center flex-shrink-0"
              size={24}
            />
          </button>
        ))}

        {visible.length === 0 && (
          <div className="py-10 text-center text-sm text-slate-500">
            조건에 맞는 공고가 없습니다.
          </div>
        )}

        <Pagination
          pages={pages}
          page={page}
          onChange={(p) => {
            setPage(p);

            window.scrollTo({
              top: 0,
              behavior: "smooth",
            });

            showToast(`${p}페이지로 이동했습니다.`);
          }}
        />
      </div>
    </UserLayout>
  );
}
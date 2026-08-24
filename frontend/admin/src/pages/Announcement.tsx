import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import AnnouncementDetail from './AnnouncementDetail';

export interface Notice {
  id: number;
  title: string;
  region: string;
  notice_type: string;
  noticeDate: string;
  status: string;
  collect: string;
  endDate?: string;
}

const collectionStatusLabel: Record<string, string> = {
  running: '수집중',
  success: '수집완료',
  partial: '부분완료',
  failed: '수집실패',
};

function getBadgeClass(value: string) {
  if (/success|완료|공고중/.test(value)) return "badge green";
  if (/running|partial|수집중/.test(value)) return "badge orange";
  if (/failed|실패|오류/.test(value)) return "badge red";
  return "badge gray";
}

export default function Announcement() {
  const navigate = useNavigate();
  const [notices, setNotices] = useState<Notice[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState('');
  const [collect, setCollect] = useState('');
  const [page, setPage] = useState(1);
  
  const [selectedNoticeId, setSelectedNoticeId] = useState<number | null>(null);

  useEffect(() => {
    fetchNotices();
  }, [page]); // page 변경 시 자동 페칭

  const fetchNotices = async () => {
    try {
      setIsLoading(true);
      const query = new URLSearchParams({
        page: page.toString(),
        size: '10',
        ...(keyword && { search: keyword }),
        ...(status && { announcement_status: status }),
        ...(collect && { collection_status: collect }),
      });

      const res = await fetch(`/api/admin/announcements?${query}`, { credentials: 'include' });
      
      if (res.status === 401) { navigate('/'); return; }
      if (!res.ok) throw new Error('조회 실패');
      
      const data = await res.json();
      
      const mappedItems: Notice[] = (data.items || []).map((item: any) => ({
        id: item.id,
        title: item.title,
        region: item.region || '-',
        notice_type: item.notice_type || '-',
        noticeDate: item.announcement_date || '-',
        status: item.announcement_status || '상태 미확인',
        collect: item.collection_status || '미수집',
        endDate: item.application_end || '-',
      }));

      setNotices(mappedItems);
      setTotalCount(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = () => {
    if (page === 1) fetchNotices();
    else setPage(1); // 1페이지로 가면 useEffect가 fetchNotices를 호출함
  };

  if (selectedNoticeId) {
    return <AnnouncementDetail id={selectedNoticeId} onBack={() => { setSelectedNoticeId(null); fetchNotices(); }} />;
  }

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>공고 관리</h1>
          <p>수집된 공고 목록과 수집 상태를 조회하고 관리합니다.</p>
        </div>
        <button className="btn btn-primary" onClick={async () => {
          const res = await fetch('/api/admin/announcements/collect', { method: 'POST', credentials: 'include' });
          if (res.ok) { alert('수집 요청 완료'); fetchNotices(); }
        }}>＋ 공고 수집</button>
      </div>
      
      <section className="card filters">
        <input className="input wide" placeholder="공고명 검색" value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSearch()} />
        <input className="input" placeholder="공고 상태 (예: 공고중)" value={status} onChange={(e) => setStatus(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSearch()} />
        <select className="select" value={collect} onChange={(e) => setCollect(e.target.value)}>
          <option value="">수집 상태 전체</option>
          <option value="running">수집중</option>
          <option value="success">수집완료</option>
          <option value="partial">부분완료</option>
          <option value="failed">수집실패</option>
        </select>
        <button className="btn btn-primary" onClick={handleSearch}>검색</button>
      </section>
      
      <section className="card table-card">
        <div className="table-toolbar">
          <b>총 {totalCount}건</b>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '70px', textAlign: 'center' }}>ID</th>
                <th>공고명</th>
                <th>유형</th>
                <th>지역</th>
                <th>공고일</th>
                <th>공고 상태</th>
                <th>수집 상태</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={8} className="empty">데이터를 불러오는 중입니다...</td></tr>
              ) : notices.length > 0 ? (
                notices.map((n) => (
                  <tr key={n.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedNoticeId(n.id)}>
                    <td style={{ textAlign: 'center' }}>{n.id}</td>
                    <td className="title-cell">{n.title}</td>
                    <td>{n.notice_type}</td>
                    <td>{n.region}</td>
                    <td>{n.noticeDate}</td>
                    <td><span className={getBadgeClass(n.status)}>{n.status}</span></td>
                    <td><span className={getBadgeClass(n.collect)}>{collectionStatusLabel[n.collect] || n.collect}</span></td>
                    <td onClick={e => e.stopPropagation()}>
                      <button className="btn btn-outline" style={{ height: '30px', padding: '0 10px', fontSize: '12px' }} onClick={() => setSelectedNoticeId(n.id)}>상세</button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={8} className="empty">결과가 없습니다.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="pagination">
          {Array.from({ length: totalPages }, (_, i) => (
            <button key={i + 1} className={i + 1 === page ? "active" : ""} onClick={() => setPage(i + 1)}>{i + 1}</button>
          ))}
        </div>
      </section>
    </main>
  );
}
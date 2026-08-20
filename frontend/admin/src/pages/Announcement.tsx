import { useState, useEffect } from 'react';
import AnnouncementDetail from './AnnouncementDetail';

// 백엔드에서 내려주는 데이터 타입
export interface Notice {
  id: number;
  title: string;
  region: string;
  noticeDate: string;
  status: string;
  collect: string;
  org?: string;
  num?: string;
  category?: string;
  endDate?: string;
  views?: number;
  files?: any[];
  content?: string;
}

function getBadgeClass(value: string) {
  let color = "gray";
  if (/완료|공고중|정상|해결완료/.test(value)) color = "green";
  else if (/진행|처리중|분석중|해결중/.test(value)) color = "orange";
  else if (/실패|오류|미해결/.test(value)) color = "red";
  else if (/대기|예정|접수중/.test(value)) color = "blue";
  return `badge ${color}`;
}

export default function Announcement() {
  const [notices, setNotices] = useState<Notice[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState('');
  const [collect, setCollect] = useState('');
  const [page, setPage] = useState(1);
  const [selectedNotice, setSelectedNotice] = useState<Notice | null>(null);
  
  const perPage = 6;

  // 컴포넌트 마운트 시 공고 목록 데이터 로드
  useEffect(() => {
    fetchNotices();
  }, []);

  const fetchNotices = async () => {
    try {
      setIsLoading(true);
      
      // 🔓 [실제 API 연동 시 주석 해제] 백엔드에서 목록 불러오기
      // const res = await fetch('/api/admin/notices');
      // const data = await res.json();
      // setNotices(data);
      
      // 🗑️ [실제 API 연동 시 삭제] 테스트용 임시 빈 배열
      setNotices([]); 
      
    } catch (error) {
      console.error('공고 목록을 불러오는 중 오류 발생:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCollectRequest = async () => {
    try {
      // 🔓 [실제 API 연동 시 주석 해제] 공고 수집 요청 보내기
      // await fetch('/api/admin/notices/collect', { method: 'POST' });
      
      alert('공고 수집 작업을 요청했습니다.');
      fetchNotices(); // 수집 후 최신 목록으로 새로고침
    } catch (error) {
      alert('수집 요청에 실패했습니다.');
    }
  };

  const filteredNotices = notices.filter(n => {
    const matchKeyword = !keyword || n.title.toLowerCase().includes(keyword.toLowerCase());
    const matchStatus = !status || n.status === status;
    const matchCollect = !collect || n.collect === collect;
    return matchKeyword && matchStatus && matchCollect;
  });

  const totalPages = Math.max(1, Math.ceil(filteredNotices.length / perPage));
  const currentRows = filteredNotices.slice((page - 1) * perPage, page * perPage);

  if (selectedNotice) {
    return (
      <AnnouncementDetail 
        notice={selectedNotice} 
        onBack={() => {
          setSelectedNotice(null);
          fetchNotices(); // 상세페이지에서 작업 후 돌아왔을 때 최신 데이터 반영
        }} 
      />
    );
  }

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>공고 관리</h1>
          <p>수집된 공고 목록과 수집 상태를 조회하고 관리합니다.</p>
        </div>
        <button className="btn btn-primary" onClick={handleCollectRequest}>＋ 공고 수집</button>
      </div>
      
      <section className="card filters">
        <input className="input wide" placeholder="공고명 검색" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">공고 상태 전체</option><option>공고중</option><option>접수중</option><option>마감</option>
        </select>
        <select className="select" value={collect} onChange={(e) => setCollect(e.target.value)}>
          <option value="">수집 상태 전체</option><option>수집완료</option><option>수집실패</option>
        </select>
        <button className="btn btn-primary" onClick={() => setPage(1)}>검색</button>
        <button className="btn btn-outline" onClick={() => { setKeyword(''); setStatus(''); setCollect(''); setPage(1); }}>초기화</button>
      </section>
      
      <section className="card table-card">
        <div className="table-toolbar">
          <b>총 {filteredNotices.length}건</b>
          <button className="btn btn-outline">목록 다운로드</button>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>ID</th><th>공고명</th><th>지역</th><th>공고일</th><th>공고 상태</th><th>수집 상태</th><th>작업</th></tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={7} className="empty" style={{ padding: '40px 0', textAlign: 'center' }}>데이터를 불러오는 중입니다...</td></tr>
              ) : currentRows.length > 0 ? (
                currentRows.map(n => (
                  <tr key={n.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedNotice(n)}>
                    <td>{n.id}</td>
                    <td className="title-cell">{n.title}</td>
                    <td>{n.region}</td>
                    <td>{n.noticeDate}</td>
                    <td><span className={getBadgeClass(n.status)}>{n.status}</span></td>
                    <td><span className={getBadgeClass(n.collect)}>{n.collect}</span></td>
                    <td onClick={e => e.stopPropagation()}>
                      <button className="btn btn-outline" style={{ height: '30px', padding: '0 10px', fontSize: '12px' }} onClick={() => setSelectedNotice(n)}>상세</button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={7} className="empty" style={{ padding: '40px 0', textAlign: 'center' }}>검색 결과가 없습니다.</td></tr>
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
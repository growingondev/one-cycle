import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ErrorDetail from './ErrorDetail';

export interface ErrorItem {
  id: number;
  time: string;
  type: string;
  stage: string;
  target: string;
  message: string;
  status: string;
}

const errorTypeLabel: Record<string, string> = {
  collection: '공고 수집', download: '파일 다운로드', parsing: '문서 파싱', normalizing: '정규화', 
  structuring: '구조화', verification: '검증', chunking: '청킹', embedding: '임베딩', database: '데이터베이스', rag: 'RAG', llm: 'LLM'
};

const statusToDisplay: Record<string, string> = { unresolved: '미해결', in_progress: '해결중', resolved: '해결완료' };

export default function ErrorPage() {
  const navigate = useNavigate();
  const [errorsList, setErrorsList] = useState<ErrorItem[]>([]);
  const [listTotal, setListTotal] = useState(0);
  const [stats, setStats] = useState({ total: 0, unresolved: 0, in_progress: 0, resolved: 0 });
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);

  const [keyword, setKeyword] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [selectedErrorId, setSelectedErrorId] = useState<number | null>(null);

  useEffect(() => {
    fetchErrors();
    fetchStats();
  }, [page]);

  const fetchStats = async () => {
    const fetchCount = async (st: string) => {
      const res = await fetch(`/api/admin/errors?page=1&size=1${st ? `&status=${st}` : ''}`, { credentials: 'include' });
      if (res.status === 401) { throw new Error('401'); }
      if (!res.ok) return 0;
      return (await res.json()).total || 0;
    };
    try {
      const [total, unresolved, in_progress, resolved] = await Promise.all([fetchCount(''), fetchCount('unresolved'), fetchCount('in_progress'), fetchCount('resolved')]);
      setStats({ total, unresolved, in_progress, resolved });
    } catch (e: any) {
      if (e.message === '401') navigate('/');
    }
  };

  const fetchErrors = async () => {
    try {
      setIsLoading(true);
      const query = new URLSearchParams({
        page: page.toString(), size: '10',
        ...(keyword && { search: keyword }),
        ...(type && { error_type: type }),
        ...(status && { status }),
      });

      const res = await fetch(`/api/admin/errors?${query}`, { credentials: 'include' });
      if (res.status === 401) { navigate('/'); return; }
      if (!res.ok) { alert('서버 오류로 인해 오류 목록을 불러올 수 없습니다.'); return; }
      
      const data = await res.json();
      const mappedItems = (data.items || []).map((item: any) => ({
        id: item.id,
        time: item.created_at || '-',
        type: item.error_type || '-',
        stage: item.stage || '-',
        target: [item.announcement_title, item.document_name].filter(Boolean).join(' / ') || '-',
        message: item.message || '-',
        status: item.status || 'unresolved',
      }));

      setErrorsList(mappedItems);
      setListTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = () => page === 1 ? fetchErrors() : setPage(1);

  if (selectedErrorId) {
    return <ErrorDetail id={selectedErrorId} onBack={() => { setSelectedErrorId(null); fetchErrors(); fetchStats(); }} />;
  }

  return (
    <main className="content">
      <div className="page-head">
        <div><h1>오류 관리</h1><p>수집, 문서 처리 및 분석 중 발생한 오류를 관리합니다.</p></div>
      </div>

      <section className="stats">
        <div className="card stat"><small>전체 오류</small><strong>{stats.total}</strong></div>
        <div className="card stat"><small>미해결</small><strong>{stats.unresolved}</strong></div>
        <div className="card stat"><small>해결 중</small><strong>{stats.in_progress}</strong></div>
        <div className="card stat"><small>해결 완료</small><strong>{stats.resolved}</strong></div>
      </section>

      <section className="card filters">
        <input className="input wide" placeholder="오류 내용 검색" value={keyword} onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} />
        <select className="select" value={type} onChange={e => setType(e.target.value)}>
          <option value="">오류 유형 전체</option>
          {Object.entries(errorTypeLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="select" value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">처리 상태 전체</option>
          <option value="unresolved">미해결</option>
          <option value="in_progress">해결중</option>
          <option value="resolved">해결완료</option>
        </select>
        <button className="btn btn-primary" onClick={handleSearch}>검색</button>
      </section>

      <section className="card table-card">
        <div className="table-toolbar"><b>총 {listTotal}건</b></div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>ID</th><th>발생 일시</th><th>유형</th><th>단계</th><th>대상</th><th>오류 내용</th><th>상태</th><th>작업</th></tr>
            </thead>
            <tbody>
              {isLoading ? <tr><td colSpan={8} className="empty">불러오는 중...</td></tr> : 
               errorsList.length > 0 ? errorsList.map((e) => (
                <tr key={e.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedErrorId(e.id)}>
                  <td>{e.id}</td><td>{e.time}</td><td>{errorTypeLabel[e.type] || e.type}</td><td>{e.stage}</td>
                  <td style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.target}</td>
                  <td className="title-cell">{e.message}</td>
                  <td><span className={`badge ${e.status === 'resolved' ? 'green' : e.status === 'in_progress' ? 'orange' : 'red'}`}>{statusToDisplay[e.status]}</span></td>
                  <td onClick={evt => evt.stopPropagation()}><button className="btn btn-outline" style={{ height: '30px', padding: '0 10px', fontSize: '12px' }} onClick={() => setSelectedErrorId(e.id)}>상세</button></td>
                </tr>
              )) : <tr><td colSpan={8} className="empty">검색 결과가 없습니다.</td></tr>}
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
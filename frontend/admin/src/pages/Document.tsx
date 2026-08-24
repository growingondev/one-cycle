import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DocumentDetail from './DocumentDetail'; // ❗ 이 파일 새로 생성해야 함

export interface DocumentItem {
  id: number;
  targetNotice: string;
  docName: string;
  type: string;
  size: string;
  regDate: string;
  processStatus: string;
  analysisStatus: string;
  downloadStatus: string;
}

const processingStatusLabel: Record<string, string> = { pending: '대기', running: '처리중', succeeded: '처리완료', failed: '처리실패' };
const analysisStatusLabel: Record<string, string> = { not_run: '미실행', pending: '대기', pass: '검증통과', warning: '경고', fail: '검증실패' };

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

export default function Document() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [stats, setStats] = useState({ total: 0, succeeded: 0, running: 0, failed: 0 });
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);

  const [keyword, setKeyword] = useState('');
  const [docType, setDocType] = useState('');
  const [processStatus, setProcessStatus] = useState('');
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [page, setPage] = useState(1);
  
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);

  useEffect(() => {
    fetchDocuments();
    fetchStats();
  }, [page]);

  const fetchStats = async () => {
    const fetchCount = async (status: string) => {
      const res = await fetch(`/api/admin/documents?page=1&size=1${status ? `&processing_status=${status}` : ''}`, { credentials: 'include' });
      return res.ok ? (await res.json()).total : 0;
    };
    const [total, succeeded, running, failed] = await Promise.all([fetchCount(''), fetchCount('succeeded'), fetchCount('running'), fetchCount('failed')]);
    setStats({ total, succeeded, running, failed });
  };

  const fetchDocuments = async () => {
    try {
      setIsLoading(true);
      const query = new URLSearchParams({
        page: page.toString(), size: '10',
        ...(keyword && { search: keyword }),
        ...(docType && { document_type: docType }),
        ...(processStatus && { processing_status: processStatus }),
        ...(analysisStatus && { analysis_status: analysisStatus }),
      });

      const res = await fetch(`/api/admin/documents?${query}`, { credentials: 'include' });
      if (res.status === 401) { navigate('/'); return; }
      
      const data = await res.json();
      const mappedItems = (data.items || []).map((item: any) => ({
        id: item.id,
        targetNotice: item.announcement_title || '-',
        docName: item.document_name || item.file_name || '-',
        type: item.document_type || '-',
        size: formatFileSize(item.file_size),
        regDate: item.created_at || '-',
        processStatus: item.processing_status,
        analysisStatus: item.analysis_status,
        downloadStatus: item.download_status,
      }));

      setDocuments(mappedItems);
      setTotalPages(data.total_pages || 1);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = () => page === 1 ? fetchDocuments() : setPage(1);

  const handleDownload = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await fetch(`/api/admin/documents/${id}/download`, { credentials: 'include' });
      if (res.status === 401) { navigate('/'); return; }
      if (res.status === 404) { alert('해당 문서가 없습니다.'); return; }
      if (res.status === 409) { alert('다운로드 가능한 파일이 없습니다.'); return; }
      if (!res.ok) throw new Error();

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `document_${id}`; 
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch {
      alert('다운로드 중 오류가 발생했습니다.');
    }
  };

  if (selectedDocId) {
    return <DocumentDetail id={selectedDocId} onBack={() => { setSelectedDocId(null); fetchDocuments(); }} />;
  }

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>문서 관리</h1>
          <p>공고에 연결된 문서의 처리 및 AI 분석 상태를 확인합니다.</p>
        </div>
      </div>

      <section className="stats">
        <div className="card stat"><small>전체 문서</small><strong>{stats.total}</strong></div>
        <div className="card stat"><small>처리 완료</small><strong>{stats.succeeded}</strong></div>
        <div className="card stat"><small>처리 중</small><strong>{stats.running}</strong></div>
        <div className="card stat"><small>처리 실패</small><strong>{stats.failed}</strong></div>
      </section>

      <section className="card filters" style={{ gridTemplateColumns: 'minmax(240px, 1fr) repeat(3, 1fr) auto' }}>
        <input className="input wide" placeholder="문서 검색" value={keyword} onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} />
        <select className="select" value={docType} onChange={e => setDocType(e.target.value)}>
          <option value="">형식 전체</option>
          <option value="hwp">HWP</option>
          <option value="hwpx">HWPX</option>
        </select>
        <select className="select" value={processStatus} onChange={e => setProcessStatus(e.target.value)}>
          <option value="">처리상태 전체</option>
          <option value="pending">대기</option>
          <option value="running">처리중</option>
          <option value="succeeded">처리완료</option>
          <option value="failed">처리실패</option>
        </select>
        <select className="select" value={analysisStatus} onChange={e => setAnalysisStatus(e.target.value)}>
          <option value="">분석상태 전체</option>
          <option value="not_run">미실행</option>
          <option value="pending">대기</option>
          <option value="pass">검증통과</option>
          <option value="warning">경고</option>
          <option value="fail">검증실패</option>
        </select>
        <button className="btn btn-primary" onClick={handleSearch}>검색</button>
      </section>

      <section className="card table-card">
        <div className="table-toolbar"><b>총 {stats.total}건</b></div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th><th>연결 공고</th><th>문서명</th><th>유형</th><th>크기</th><th>처리 상태</th><th>분석 상태</th><th>작업</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={8} className="empty">불러오는 중...</td></tr>
              ) : documents.map((d) => (
                <tr key={d.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedDocId(d.id)}>
                  <td>{d.id}</td>
                  <td style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.targetNotice}</td>
                  <td className="title-cell">{d.docName}</td>
                  <td>{d.type}</td>
                  <td>{d.size}</td>
                  <td><span className={`badge ${d.processStatus === 'succeeded' ? 'green' : d.processStatus === 'failed' ? 'red' : 'orange'}`}>{processingStatusLabel[d.processStatus] || d.processStatus}</span></td>
                  <td><span className={`badge ${d.analysisStatus === 'pass' ? 'green' : d.analysisStatus === 'fail' ? 'red' : 'gray'}`}>{analysisStatusLabel[d.analysisStatus] || d.analysisStatus}</span></td>
                  <td onClick={e => e.stopPropagation()}>
                    <button className="btn btn-outline" disabled={d.downloadStatus !== 'completed'} onClick={(e) => handleDownload(d.id, e)}>다운로드</button>
                  </td>
                </tr>
              ))}
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
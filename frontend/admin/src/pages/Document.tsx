import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export interface DocumentItem {
  id: number;
  targetNotice: string;
  docName: string;
  type: string;
  size: string;
  regDate: string;
  processStatus: string;
  analysisStatus: string;
}

function getStatusBadge(status: string) {
  if (/완료|성공/.test(status)) return 'green';
  if (/중|진행/.test(status)) return 'orange';
  if (/실패|오류/.test(status)) return 'red';
  if (/대기/.test(status)) return 'blue';
  return 'gray';
}

export default function Document() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [keyword, setKeyword] = useState('');
  const [docType, setDocType] = useState('');
  const [processStatus, setProcessStatus] = useState('');
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [page, setPage] = useState(1);
  
  const perPage = 10;

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      setIsLoading(true);
      const res = await fetch('/api/admin/documents', {
        credentials: 'include',
      });
      if (res.status === 401) { navigate('/'); return; }
      if (!res.ok) throw new Error('문서 목록 조회 실패');
      
      const data = await res.json();
      const rawItems = Array.isArray(data) ? data : data.items || [];

      const mappedItems: DocumentItem[] = rawItems.map((item: any) => ({
        id: item.id,
        targetNotice: item.announcement_title || '-',
        docName: item.file_name || '-',
        type: item.document_type || '-',
        size: `${item.file_size || 0} KB`,
        regDate: item.created_at || '-',
        processStatus: item.processing_status || '미처리',
        analysisStatus: item.analysis_status || '대기',
      }));

      setDocuments(mappedItems);
    } catch (error) {
      console.error('문서 목록을 불러오는 중 오류 발생:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = (id: number) => {
    window.open(`/api/admin/documents/${id}/download`, '_blank');
  };

  const filteredDocs = documents.filter(d => {
    const matchKeyword = !keyword || d.docName.toLowerCase().includes(keyword.toLowerCase()) || d.targetNotice.toLowerCase().includes(keyword.toLowerCase());
    const matchType = !docType || d.type === docType;
    const matchProcess = !processStatus || d.processStatus === processStatus;
    const matchAnalysis = !analysisStatus || d.analysisStatus === analysisStatus;
    return matchKeyword && matchType && matchProcess && matchAnalysis;
  });

  const totalPages = Math.max(1, Math.ceil(filteredDocs.length / perPage));
  const currentRows = filteredDocs.slice((page - 1) * perPage, page * perPage);

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>문서 관리</h1>
          <p>공고에 연결된 문서의 처리 및 AI 분석 상태를 확인합니다.</p>
        </div>
        <button className="btn btn-outline" onClick={fetchDocuments}>↻ 새로고침</button>
      </div>

      <section className="stats">
        <div className="card stat"><small>전체 문서</small><strong>{documents.length}</strong></div>
        <div className="card stat"><small>처리 완료</small><strong>{documents.filter(d => d.processStatus.includes('완료')).length}</strong></div>
        <div className="card stat"><small>처리 중</small><strong>{documents.filter(d => d.processStatus.includes('중')).length}</strong></div>
        <div className="card stat"><small>처리 실패</small><strong>{documents.filter(d => d.processStatus.includes('실패')).length}</strong></div>
      </section>

      <section className="card filters" style={{ gridTemplateColumns: 'minmax(240px, 1fr) repeat(3, 1fr) auto' }}>
        <input className="input wide" placeholder="공고명 또는 문서명 검색" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        <select className="select" value={docType} onChange={(e) => setDocType(e.target.value)}>
          <option value="">문서 유형 전체</option>
          <option value="공고문">공고문</option>
          <option value="정정공고문">정정공고문</option>
        </select>
        <select className="select" value={processStatus} onChange={(e) => setProcessStatus(e.target.value)}>
          <option value="">처리 상태 전체</option>
          <option value="완료">완료</option>
          <option value="진행중">진행중</option>
          <option value="실패">실패</option>
        </select>
        <select className="select" value={analysisStatus} onChange={(e) => setAnalysisStatus(e.target.value)}>
          <option value="">분석 상태 전체</option>
          <option value="완료">완료</option>
          <option value="대기">대기</option>
        </select>
        <button className="btn btn-primary" onClick={() => setPage(1)}>검색</button>
      </section>

      <section className="card table-card">
        <div className="table-toolbar">
          <b>총 {filteredDocs.length}건</b>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '70px', textAlign: 'center' }}>번호</th>
                <th>연결 공고</th>
                <th>문서명</th>
                <th>유형</th>
                <th>크기</th>
                <th>등록일</th>
                <th>처리 상태</th>
                <th>분석 상태</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={9} className="empty" style={{ padding: '40px 0', textAlign: 'center' }}>데이터를 불러오는 중입니다...</td></tr>
              ) : currentRows.length > 0 ? (
                currentRows.map((d, idx) => {
                  const rowNumber = filteredDocs.length - ((page - 1) * perPage + idx);
                  return (
                    <tr key={d.id}>
                      <td style={{ textAlign: 'center' }}>{rowNumber}</td>
                      <td style={{ maxWidth: '180px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.targetNotice}</td>
                      <td className="title-cell">{d.docName}</td>
                      <td>{d.type}</td>
                      <td>{d.size}</td>
                      <td>{d.regDate}</td>
                      <td><span className={`badge ${getStatusBadge(d.processStatus)}`}>{d.processStatus}</span></td>
                      <td><span className={`badge ${getStatusBadge(d.analysisStatus)}`}>{d.analysisStatus}</span></td>
                      <td>
                        <button className="btn btn-outline" style={{ height: '30px', padding: '0 10px', fontSize: '12px' }} onClick={() => handleDownload(d.id)}>다운로드</button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr><td colSpan={9} className="empty" style={{ padding: '40px 0', textAlign: 'center' }}>검색 결과가 없습니다.</td></tr>
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
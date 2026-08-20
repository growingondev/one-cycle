import { useState, useEffect } from 'react';
import ErrorDetail from './ErrorDetail';

export interface ErrorItem {
  id: number;
  time: string;
  type: string;
  step: string;
  target: string;
  message: string;
  status: string;
  code?: string;
  level?: string;
  method?: string;
  url?: string;
  stack?: string;
  history?: any[];
}

function getBadgeClass(value: string) {
  let color = "gray";
  if (/완료|공고중|정상|해결완료/.test(value)) color = "green";
  else if (/진행|처리중|분석중|해결중/.test(value)) color = "orange";
  else if (/실패|오류|미해결/.test(value)) color = "red";
  else if (/대기|예정|접수중/.test(value)) color = "blue";
  return `badge ${color}`;
}

export default function ErrorPage() {
  const [errorsList, setErrorsList] = useState<ErrorItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [keyword, setKeyword] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [selectedError, setSelectedError] = useState<ErrorItem | null>(null);

  const perPage = 10;

  useEffect(() => {
    fetchErrors();
  }, []);

  const fetchErrors = async () => {
    try {
      setIsLoading(true);
      const token = sessionStorage.getItem('access_token');
      const res = await fetch('/api/admin/errors', {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        }
      });
      if (!res.ok) throw new Error('오류 목록 조회 실패');
      const data = await res.json();
      setErrorsList(Array.isArray(data) ? data : data.items || []);
    } catch (error) {
      console.error('오류 목록 로드 실패', error);
    } finally {
      setIsLoading(false);
    }
  };

  const filteredErrors = errorsList.filter(e => {
    const matchKeyword = !keyword || (e.target + e.message).toLowerCase().includes(keyword.toLowerCase());
    const matchType = !type || e.type === type;
    const matchStatus = !status || e.status === status;
    return matchKeyword && matchType && matchStatus;
  });

  const totalPages = Math.max(1, Math.ceil(filteredErrors.length / perPage));
  const currentRows = filteredErrors.slice((page - 1) * perPage, page * perPage);

  if (selectedError) {
    return (
      <ErrorDetail 
        error={selectedError} 
        onBack={() => {
          setSelectedError(null);
          fetchErrors();
        }} 
      />
    );
  }

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>오류 관리</h1>
          <p>수집, 문서 처리 및 AI 분석 과정에서 발생한 오류를 관리합니다.</p>
        </div>
        <button className="btn btn-outline" onClick={() => window.open('/api/admin/errors/export')}>목록 다운로드</button>
      </div>

      <section className="stats">
        <div className="card stat"><small>전체 오류</small><strong>{errorsList.length}</strong></div>
        <div className="card stat"><small>미해결</small><strong>{errorsList.filter(e => e.status === '미해결').length}</strong></div>
        <div className="card stat"><small>해결 중</small><strong>{errorsList.filter(e => e.status === '해결중').length}</strong></div>
        <div className="card stat"><small>해결 완료</small><strong>{errorsList.filter(e => e.status === '해결완료').length}</strong></div>
      </section>

      <section className="card filters">
        <input className="input wide" placeholder="공고명 또는 오류 내용 검색" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        <select className="select" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">오류 유형 전체</option>
          <option value="공고 수집">공고 수집</option>
          <option value="문서 처리">문서 처리</option>
          <option value="AI 분석">AI 분석</option>
        </select>
        <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">처리 상태 전체</option>
          <option value="미해결">미해결</option>
          <option value="해결중">해결중</option>
          <option value="해결완료">해결완료</option>
        </select>
        <button className="btn btn-primary" onClick={() => setPage(1)}>검색</button>
      </section>

      <section className="card table-card">
        <div className="table-toolbar">
          <b>총 {filteredErrors.length}건</b>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '70px', textAlign: 'center' }}>번호</th>
                <th>발생 일시</th>
                <th>오류 유형</th>
                <th>발생 구간</th>
                <th>대상 공고</th>
                <th>오류 내용</th>
                <th>처리 상태</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={8} className="empty" style={{ padding: '40px 0', textAlign: 'center' }}>데이터를 불러오는 중입니다...</td></tr>
              ) : currentRows.length > 0 ? (
                currentRows.map((e, idx) => {
                  const rowNumber = filteredErrors.length - ((page - 1) * perPage + idx);
                  return (
                    <tr key={e.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedError(e)}>
                      <td style={{ textAlign: 'center' }}>{rowNumber}</td>
                      <td>{e.time}</td>
                      <td>{e.type}</td>
                      <td>{e.step}</td>
                      <td>{e.target}</td>
                      <td className="title-cell">{e.message}</td>
                      <td><span className={getBadgeClass(e.status)}>{e.status}</span></td>
                      <td onClick={evt => evt.stopPropagation()}>
                        <button className="btn btn-outline" style={{ height: '30px', padding: '0 10px', fontSize: '12px' }} onClick={() => setSelectedError(e)}>상세</button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr><td colSpan={8} className="empty" style={{ padding: '40px 0', textAlign: 'center' }}>검색 결과가 없습니다.</td></tr>
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
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const statusToDisplay: Record<string, string> = { unresolved: '미해결', in_progress: '해결중', resolved: '해결완료' };
const getStatusColor = (s: string) => s === 'resolved' ? 'var(--green)' : s === 'in_progress' ? 'var(--orange)' : 'var(--red)'; 

interface ErrorDetailProps {
  id: number;
  onBack: () => void;
}

export default function ErrorDetail({ id, onBack }: ErrorDetailProps) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<any>(null);
  const [status, setStatus] = useState('unresolved');
  const [note, setNote] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        const res = await fetch(`/api/admin/errors/${id}`, { credentials: 'include' });
        if (res.status === 401) { navigate('/'); return; }
        if (res.status === 404) { alert('오류 정보를 찾을 수 없습니다.'); onBack(); return; }
        if (!res.ok) { alert('오류 상세 정보를 불러오는 중 서버 문제가 발생했습니다.'); setFetchError(true); onBack(); return; }
        const data = await res.json();
        setDetail(data);
        setStatus(data.status);
      } catch {
        alert('네트워크 오류가 발생했습니다.');
        onBack();
      }
    };
    fetchDetail();
  }, [id, navigate, onBack]);

  const handleStatusChange = async (apiStatus: string) => {
    try {
      setIsUpdating(true);
      const res = await fetch(`/api/admin/errors/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ 
          status: apiStatus, 
          resolution: note.trim() || null 
        })
      });

      if (res.status === 401) { navigate('/'); return; }
      if (!res.ok) { alert('서버 오류로 인해 상태 변경에 실패했습니다.'); return; }
      
      const updated = await res.json();
      setDetail(updated);         // 전체 데이터(해결 시각, 메모 등) 교체
      setStatus(updated.status);  // 상태 동기화
      setNote('');                // 입력창 초기화
      alert('상태가 변경되었습니다.');
    } catch {
      alert('네트워크 오류가 발생했습니다.');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleRetry = async () => {
    try {
      setIsUpdating(true);
      const res = await fetch(`/api/admin/errors/${id}/retry`, { method: 'POST', credentials: 'include' });
      if (res.status === 401) { navigate('/'); return; }
      if (res.status === 409) { alert('현재 재시도 할 수 없는 상태입니다.'); return; }
      if (!res.ok) { alert('서버 오류로 인해 재시도 요청에 실패했습니다.'); return; }
      alert('오류 재시도 작업이 요청되었습니다.');
    } catch {
      alert('네트워크 오류가 발생했습니다.');
    } finally {
      setIsUpdating(false);
    }
  };

  if (fetchError || !detail) return <main className="content"><div style={{ padding: '40px', textAlign: 'center' }}>불러오는 중...</div></main>;

  return (
    <main className="content">
      <div className="page-head" style={{ marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', margin: '0 0 6px' }}>오류 상세</h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '14px' }}>오류 정보 및 상태를 관리합니다.</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-outline" onClick={handleRetry} disabled={isUpdating}>↻ 재시도</button>
          <button className="btn btn-outline" onClick={onBack}>← 목록으로</button>
        </div>
      </div>

      <div className="card" style={{ padding: '24px 32px', marginBottom: '20px', borderLeft: `4px solid ${getStatusColor(status)}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '20px' }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <span className={`badge ${status === 'resolved' ? 'green' : status === 'in_progress' ? 'orange' : 'red'}`}>{statusToDisplay[status]}</span>
            </div>
            <p style={{ margin: 0, fontSize: '16px', color: 'var(--text)' }}>{detail.message}</p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
            <div style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 700 }}>상태 변경 (메모 옵션)</div>
            <input type="text" className="input" placeholder="해결 내용 입력 (선택)" value={note} onChange={e => setNote(e.target.value)} style={{ width: '220px', marginBottom: '4px' }}/>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['unresolved', 'in_progress', 'resolved'].map((s) => (
                <button key={s} disabled={isUpdating}
                  className={`btn ${status === s ? 'btn-primary' : 'btn-outline'}`}
                  style={{ height: '32px', padding: '0 12px', fontSize: '12px', ...(status === s && { background: getStatusColor(s), borderColor: getStatusColor(s) }) }}
                  onClick={() => handleStatusChange(s)}>
                  {statusToDisplay[s]}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: '24px' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>🌐 오류 정보</div>
        <div style={{ padding: '8px 0' }}>
          {[
            { label: '오류 코드', value: detail.error_code },
            { label: '발생 시각', value: detail.created_at },
            { label: '해결 시각', value: detail.resolved_at },
            { label: '발생 단계', value: detail.stage },
            { label: '대상 공고', value: detail.announcement_title },
            { label: '대상 문서', value: detail.document_name },
            { label: '입력된 해결 내용', value: detail.resolution },
          ].map((row, idx) => (
            <div key={idx} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', padding: '12px 24px', fontSize: '14px' }}>
              <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{row.label}</span>
              <code style={{ background: '#f8f9fc', padding: '4px 8px', borderRadius: '4px', color: 'var(--text)', fontSize: '13px' }}>{row.value || '-'}</code>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
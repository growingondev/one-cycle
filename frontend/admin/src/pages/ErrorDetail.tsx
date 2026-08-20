import { useState } from 'react';
import type { ErrorItem } from './Error';

interface ErrorDetailProps {
  error: ErrorItem;
  onBack: () => void;
}

const getStatusColor = (status: string) => {
  if (status === '완료' || status === '해결완료') return 'var(--green)';
  if (status === '처리중' || status === '해결중') return 'var(--orange)';
  return 'var(--red)'; 
};

export default function ErrorDetail({ error, onBack }: ErrorDetailProps) {
  const [status, setStatus] = useState(error.status || '미해결');
  const [note, setNote] = useState('');
  const [history, setHistory] = useState<any[]>(error.history || []);
  const [isUpdating, setIsUpdating] = useState(false);

  const handleStatusChange = async (newStatus: string) => {
    try {
      setIsUpdating(true);
      const token = sessionStorage.getItem('access_token');
      const res = await fetch(`/api/admin/errors/${error.id}/status`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ status: newStatus })
      });

      if (!res.ok) throw new Error('상태 변경 실패');
      
      setStatus(newStatus);
      const autoEntry = { actor: '시스템', date: new Date().toISOString(), note: `상태가 [${newStatus}]로 변경됨` };
      setHistory(prev => [...prev, autoEntry]);
    } catch (err) {
      alert('상태 변경에 실패했습니다.');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleAddNote = async () => {
    if (!note.trim()) return;
    try {
      setIsUpdating(true);
      const token = sessionStorage.getItem('access_token');
      const res = await fetch(`/api/admin/errors/${error.id}/notes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ note })
      });

      if (!res.ok) throw new Error('메모 저장 실패');
      const newEntry = await res.json();
      setHistory(prev => [...prev, newEntry]);
      setNote('');
    } catch (err) {
      alert('메모 저장에 실패했습니다.');
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <main className="content">
      <div className="page-head" style={{ marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', margin: '0 0 6px' }}>오류 상세</h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '14px' }}>오류 정보 및 처리 이력을 확인합니다.</p>
        </div>
        <button className="btn btn-outline" onClick={onBack}>← 목록으로</button>
      </div>

      <div className="card" style={{ padding: '24px 32px', marginBottom: '20px', borderLeft: `4px solid ${getStatusColor(status)}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '20px' }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <span className={`badge ${error.level === '심각' ? 'red' : 'orange'}`}>{error.level || error.type}</span>
              <span className={`badge ${status === '해결중' ? 'orange' : status === '해결완료' ? 'green' : 'red'}`}>{status}</span>
            </div>
            <div style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '8px', fontWeight: 700 }}>오류 코드</div>
            <code style={{ display: 'inline-block', fontSize: '18px', fontWeight: 800, color: 'var(--red)', background: '#fff1f2', padding: '6px 12px', borderRadius: '6px', marginBottom: '16px' }}>
              {error.code || `ERR_${error.type}_${error.id}`}
            </code>
            <p style={{ margin: 0, fontSize: '16px', color: 'var(--text)' }}>{error.message}</p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
            <div style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 700 }}>상태 변경</div>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['미해결', '해결중', '해결완료'].map((s) => (
                <button key={s} disabled={isUpdating}
                  className={`btn ${status === s ? 'btn-primary' : 'btn-outline'}`}
                  style={{ height: '36px', padding: '0 16px', fontSize: '13px', ...(status === s && { background: getStatusColor(s), borderColor: getStatusColor(s) }) }}
                  onClick={() => handleStatusChange(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>🌐 요청 정보</div>
          <div style={{ padding: '8px 0' }}>
            {[
              { label: '발생 시각', value: error.time },
              { label: 'HTTP 메서드', value: error.method || 'GET' },
              { label: 'URL / 대상', value: error.url || error.target },
            ].map((row, idx) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', padding: '12px 24px', fontSize: '14px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{row.label}</span>
                <code style={{ background: '#f8f9fc', padding: '4px 8px', borderRadius: '4px', color: 'var(--text)', fontSize: '13px' }}>{row.value}</code>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>📊 처리 현황</div>
          <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '14px', color: 'var(--muted)' }}>처리 메모 수</span>
              <span style={{ fontWeight: 800, fontSize: '18px' }}>{history.length}건</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '14px', color: 'var(--muted)' }}>현재 상태</span>
              <span className={`badge ${status === '해결중' ? 'orange' : status === '해결완료' ? 'green' : 'red'}`}>{status}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: '24px' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>🔍 스택 트레이스</div>
        <pre style={{ margin: 0, padding: '24px 32px', fontSize: '14px', lineHeight: 1.7, background: '#0f1923', color: '#e2e8f0', overflowX: 'auto', fontFamily: '"JetBrains Mono", monospace' }}>
          {error.stack || '서버에서 스택 트레이스를 반환하지 않았습니다.'}
        </pre>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: '24px' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>📋 처리 이력</div>
        <div style={{ padding: '32px 32px 16px 32px', display: 'flex', flexDirection: 'column' }}>
          {history.length > 0 ? history.map((h, i) => (
            <div key={i} style={{ display: 'flex', gap: '20px', paddingBottom: i < history.length - 1 ? '32px' : '0', position: 'relative' }}>
              {i < history.length - 1 && <div style={{ position: 'absolute', left: '11px', top: '24px', width: '2px', height: 'calc(100% - 24px)', background: '#e4e9f1' }} />}
              <div style={{ width: '24px', height: '24px', borderRadius: '50%', flexShrink: 0, marginTop: '2px', background: i === history.length - 1 ? 'var(--blue)' : '#e4e9f1', border: '4px solid #fff', boxShadow: '0 0 0 1px #dbe2ec' }} />
              <div style={{ flex: 1, paddingBottom: '8px' }}>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'baseline', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 800, fontSize: '14px', color: 'var(--text)' }}>{h.actor}</span>
                  <span style={{ fontSize: '13px', color: 'var(--muted)' }}>{h.date?.split('T')[0] || h.date}</span>
                </div>
                <div style={{ fontSize: '15px', lineHeight: 1.6, color: 'var(--text)' }}>{h.note}</div>
              </div>
            </div>
          )) : <div style={{ color: 'var(--muted)' }}>처리 이력이 없습니다.</div>}
        </div>

        <div style={{ padding: '24px 32px', borderTop: '1px solid var(--line)', background: '#fafcff' }}>
          <div style={{ fontSize: '14px', fontWeight: 800, marginBottom: '12px' }}>처리 메모 추가</div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <input className="input" style={{ flex: 1, height: '44px' }} placeholder="처리 내용을 입력하세요..." value={note} onChange={e => setNote(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAddNote()} disabled={isUpdating} />
            <button className="btn btn-primary" style={{ height: '44px', padding: '0 24px' }} onClick={handleAddNote} disabled={isUpdating}>
              {isUpdating ? '저장 중...' : '메모 추가'}
            </button>
          </div>
        </div>
      </div>
      <div style={{ paddingBottom: '40px' }}><button className="btn btn-outline" onClick={onBack}>← 목록으로</button></div>
    </main>
  );
}
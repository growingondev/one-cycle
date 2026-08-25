import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface DocumentDetailProps {
  id: number;
  onBack: () => void;
}

export default function DocumentDetail({ id, onBack }: DocumentDetailProps) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<any>(null);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        const res = await fetch(`/api/admin/documents/${id}`, { credentials: 'include' });
        if (res.status === 401) { navigate('/'); return; }
        if (res.status === 404) { alert('문서를 찾을 수 없습니다.'); onBack(); return; }
        if (!res.ok) { alert('문서 상세 정보를 불러오는 중 서버 오류가 발생했습니다.'); setFetchError(true); onBack(); return; }
        setDetail(await res.json());
      } catch {
        alert('네트워크 오류가 발생했습니다.');
        onBack();
      }
    };
    fetchDetail();
  }, [id, navigate, onBack]);

  const handleReprocess = async () => {
    try {
      setIsReprocessing(true);
      const res = await fetch(`/api/admin/documents/${id}/reprocess`, { method: 'POST', credentials: 'include' });
      if (res.status === 401) { navigate('/'); return; }
      if (res.status === 409) { alert('현재 상태에서는 재처리할 수 없습니다.'); return; }
      if (!res.ok) { alert('서버 오류로 인해 요청에 실패했습니다.'); return; }
      alert('재처리 요청이 완료되었습니다.');
    } catch {
      alert('네트워크 오류가 발생했습니다.');
    } finally {
      setIsReprocessing(false);
    }
  };

  if (fetchError || !detail) return <main className="content"><div style={{ padding: '40px', textAlign: 'center' }}>불러오는 중...</div></main>;

  return (
    <main className="content">
      <div className="page-head" style={{ marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', margin: '0 0 6px' }}>문서 상세</h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '14px' }}>문서 구조화 및 청킹/임베딩 상태를 확인합니다.</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-outline" onClick={onBack}>← 목록으로</button>
          <button className="btn btn-outline" onClick={handleReprocess} disabled={isReprocessing}>
            {isReprocessing ? '요청 중...' : '↻ 문서 재처리'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px', marginBottom: '20px' }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>📄 문서 정보</div>
          <div style={{ padding: '8px 0' }}>
            {[
              { label: '파일명', value: detail.document_name || detail.file_name },
              { label: '저장 경로', value: detail.storage_path },
              { label: '체크섬', value: detail.checksum_sha256 },
              { label: '처리 단계', value: detail.processing?.current_stage },
              { label: '오류 메시지', value: detail.processing?.error_message },
              { label: '청킹 완료 수', value: detail.chunking?.chunk_count },
              { label: '임베딩 완료 수', value: detail.embedding?.completed_count },
            ].map((row, idx) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '150px 1fr', padding: '12px 24px', borderBottom: '1px solid #f8f9fc', fontSize: '14px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{row.label}</span>
                <span style={{ fontWeight: 500, color: 'var(--text)' }}>{row.value || '-'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
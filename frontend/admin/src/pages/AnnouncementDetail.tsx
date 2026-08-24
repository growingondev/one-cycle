import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface AnnouncementDetailProps {
  id: number;
  onBack: () => void;
}

export default function AnnouncementDetail({ id, onBack }: AnnouncementDetailProps) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<any>(null);
  const [isReCollecting, setIsReCollecting] = useState(false);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        const res = await fetch(`/api/admin/announcements/${id}`, { credentials: 'include' });
        if (res.status === 401) { navigate('/'); return; }
        if (res.status === 404) { alert('해당 공고가 없습니다.'); onBack(); return; }
        if (!res.ok) { alert('상세 정보를 불러오는 중 서버 오류가 발생했습니다.'); setFetchError(true); onBack(); return; }
        setDetail(await res.json());
      } catch {
        alert('네트워크 오류가 발생했습니다.');
        onBack();
      }
    };
    fetchDetail();
  }, [id, navigate, onBack]);

  const handleReCollect = async () => {
    try {
      setIsReCollecting(true);
      const res = await fetch(`/api/admin/announcements/${id}/recollect`, { method: 'POST', credentials: 'include' });
      if (res.status === 401) { navigate('/'); return; }
      if (!res.ok) { alert('서버 오류로 인해 재수집 요청에 실패했습니다.'); return; }
      alert('재수집 요청이 완료되었습니다.');
    } catch {
      alert('네트워크 오류가 발생했습니다.');
    } finally {
      setIsReCollecting(false);
    }
  };

  if (fetchError || !detail) return <main className="content"><div style={{ padding: '40px', textAlign: 'center' }}>불러오는 중...</div></main>;

  return (
    <main className="content">
      <div className="page-head" style={{ marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', margin: '0 0 6px' }}>공고 상세</h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '14px' }}>공고 내용을 확인하고 개별 재수집을 진행할 수 있습니다.</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-outline" onClick={onBack}>← 목록으로</button>
          <button className="btn btn-outline" onClick={handleReCollect} disabled={isReCollecting}>
            {isReCollecting ? '요청 중...' : '↻ 개별 재수집'}
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: '28px 32px', marginBottom: '20px' }}>
        <h2 style={{ margin: '0 0 12px', fontSize: '22px', color: 'var(--text)', fontWeight: 800 }}>{detail.title}</h2>
        <div style={{ color: 'var(--muted)', fontSize: '14px' }}>
          {detail.region} · 공고유형: {detail.notice_type} · 식별 ID: {detail.id}
        </div>
        {detail.detail_url && (
          <div style={{ marginTop: '12px' }}>
            <a href={detail.detail_url} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)', fontWeight: 700, fontSize: '14px' }}>🔗 원본 공고 바로가기</a>
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px', marginBottom: '20px' }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>📋 주요 정보</div>
          <div style={{ padding: '8px 0' }}>
            {[
              { label: '공고 상태', value: detail.announcement_status },
              { label: '수집 상태', value: detail.collection_status },
              { label: '접수 기간', value: detail.key_information?.application_period },
              { label: '신청 자격', value: detail.key_information?.eligibility },
              { label: '제출 서류', value: detail.key_information?.required_documents },
              { label: '문의처', value: detail.key_information?.contact_information },
              { label: '연결된 문서 수', value: `${detail.document_count || 0}건` },
            ].map((row, idx) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', padding: '12px 24px', borderBottom: '1px solid #f8f9fc', fontSize: '14px' }}>
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
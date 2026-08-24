import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Notice } from './Announcement';

interface AnnouncementDetailProps {
  notice: Notice;
  onBack: () => void;
}

const getBadgeColor = (status: string) => {
  if (status === '게시중' || status === '수집완료' || status === '공고중') return 'green';
  if (status === '마감') return 'gray';
  return 'orange'; 
};

export default function AnnouncementDetail({ notice, onBack }: AnnouncementDetailProps) {
  const navigate = useNavigate();
  const [isReCollecting, setIsReCollecting] = useState(false);

  const handleReCollect = async () => {
    try {
      setIsReCollecting(true);
      const res = await fetch(`/api/admin/announcements/${notice.id}/recollect`, {
        method: 'POST',
        credentials: 'include',
      });
      if (res.status === 401) { navigate('/'); return; }
      if (!res.ok) throw new Error('재수집 요청 실패');
      alert('해당 공고의 재수집 요청이 완료되었습니다.');
    } catch (error) {
      console.error(error);
      alert('재수집 요청에 실패했습니다.');
    } finally {
      setIsReCollecting(false);
    }
  };

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
            {isReCollecting ? '재수집 요청 중...' : '↻ 개별 재수집'}
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: '28px 32px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
          <span className={`badge ${getBadgeColor(notice.status)}`}>{notice.status || '상태없음'}</span>
        </div>
        <h2 style={{ margin: '0 0 12px', fontSize: '22px', color: 'var(--text)', fontWeight: 800 }}>{notice.title}</h2>
        <div style={{ color: 'var(--muted)', fontSize: '14px' }}>
          {notice.region} · 시스템 식별 ID: {notice.id}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px', marginBottom: '20px' }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>📋 공고 정보</div>
          <div style={{ padding: '8px 0' }}>
            {[
              { label: '지역', value: notice.region || '-' },
              { label: '게시일', value: notice.noticeDate || '-' },
              { label: '마감일', value: notice.endDate || '-' },
              { label: '공고 상태', value: notice.status || '-' },
              { label: '수집 상태', value: notice.collect || '-' },
            ].map((row, idx) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', padding: '12px 24px', borderBottom: '1px solid #f8f9fc', fontSize: '14px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{row.label}</span>
                <span style={{ fontWeight: 500, color: 'var(--text)' }}>{row.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
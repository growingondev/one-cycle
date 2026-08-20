import React, { useState } from 'react';
import type { Notice } from './Announcement';

interface AnnouncementDetailProps {
  notice: Notice;
  onBack: () => void;
}

const getBadgeColor = (status: string) => {
  if (status === '게시중' || status === '수집완료' || status === '공고중') return 'green';
  if (status === '마감') return 'gray';
  if (status === '사업공고' || status === '모집공고') return 'blue';
  return 'orange'; 
};

export default function AnnouncementDetail({ notice, onBack }: AnnouncementDetailProps) {
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isReCollecting, setIsReCollecting] = useState(false);

  // 개별 공고 재수집
  const handleReCollect = async () => {
    try {
      setIsReCollecting(true);
      const token = sessionStorage.getItem('access_token');
      const res = await fetch(`/api/admin/notices/${notice.id}/re-collect`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        }
      });
      if (!res.ok) throw new Error('재수집 요청 실패');
      alert('해당 공고의 재수집 요청이 완료되었습니다.');
    } catch (error) {
      console.error(error);
      alert('재수집 요청에 실패했습니다.');
    } finally {
      setIsReCollecting(false);
    }
  };

  // 공고 삭제
  const handleDelete = async () => {
    try {
      setIsDeleting(true);
      const token = sessionStorage.getItem('access_token');
      const res = await fetch(`/api/admin/notices/${notice.id}`, {
        method: 'DELETE',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        }
      });
      if (!res.ok) throw new Error('공고 삭제 실패');
      alert('공고가 성공적으로 삭제되었습니다.');
      onBack();
    } catch (error) {
      console.error('삭제 실패:', error);
      alert('공고 삭제에 실패했습니다.');
    } finally {
      setIsDeleting(false);
      setDeleteConfirm(false);
    }
  };

  return (
    <main className="content">
      <div className="page-head" style={{ marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', margin: '0 0 6px' }}>공고 상세</h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '14px' }}>공고 내용을 확인하고 개별 재수집 및 삭제를 진행할 수 있습니다.</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-outline" onClick={onBack}>← 목록으로</button>
          <button className="btn btn-outline" onClick={handleReCollect} disabled={isReCollecting}>
            {isReCollecting ? '재수집 요청 중...' : '↻ 개별 재수집'}
          </button>
          <button className="btn btn-outline" style={{ color: 'var(--red)', borderColor: '#ffd6d9', background: '#fff9fa' }} onClick={() => setDeleteConfirm(true)}>
            삭제
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: '28px 32px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
          <span className={`badge ${getBadgeColor(notice.status)}`}>{notice.status || '상태없음'}</span>
          {notice.category && <span className={`badge ${getBadgeColor(notice.category)}`}>{notice.category}</span>}
        </div>
        <h2 style={{ margin: '0 0 12px', fontSize: '22px', color: 'var(--text)', fontWeight: 800 }}>{notice.title}</h2>
        <div style={{ color: 'var(--muted)', fontSize: '14px' }}>
          {notice.org || notice.region} · 시스템 식별 ID: {notice.id} {notice.num ? `(공고번호: ${notice.num})` : ''}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>📋 공고 정보</div>
          <div style={{ padding: '8px 0' }}>
            {[
              { label: '기관명/지역', value: notice.org || notice.region || '-' },
              { label: '공고번호', value: notice.num || notice.id },
              { label: '분류', value: notice.category || '기본분류' },
              { label: '게시 시작일', value: notice.noticeDate || '-' },
              { label: '마감일', value: notice.endDate || '-' },
              { label: '조회수', value: notice.views ? `${notice.views.toLocaleString()}회` : '0회' },
            ].map((row, idx) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', padding: '12px 24px', borderBottom: '1px solid #f8f9fc', fontSize: '14px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{row.label}</span>
                <span style={{ fontWeight: 500, color: 'var(--text)' }}>{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>
            📎 첨부파일 ({notice.files?.length || 0}개)
          </div>
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {notice.files && notice.files.length > 0 ? notice.files.map((file: any, idx: number) => (
              <div 
                key={idx} 
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: '#f8f9fc', borderRadius: '8px', border: '1px solid #edf0f4', cursor: 'pointer' }}
                onClick={() => window.open(file.url || `/api/admin/documents/${file.id}/download`)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span style={{ fontSize: '24px' }}>{file.name?.includes('.pdf') ? '📄' : '📎'}</span>
                  <div>
                    <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text)', marginBottom: '4px' }}>{file.name}</div>
                    <div style={{ fontSize: '12px', color: 'var(--muted)' }}>{file.size || '용량 정보 없음'}</div>
                  </div>
                </div>
                <span style={{ color: 'var(--blue)', fontSize: '13px', fontWeight: 700 }}>↓ 다운로드</span>
              </div>
            )) : <div style={{ textAlign: 'center', padding: '20px', color: 'var(--muted)' }}>등록된 첨부파일이 없습니다.</div>}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: '24px' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--line)', fontWeight: 800, fontSize: '15px' }}>📃 공고 내용</div>
        <div style={{ padding: '32px 36px', lineHeight: 1.8, fontSize: '15px', color: 'var(--text)', whiteSpace: 'pre-line' }}>
          {notice.content || '공고 내용이 없습니다.'}
        </div>
      </div>

      {deleteConfirm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
          <div className="card" style={{ width: '380px', padding: '30px', boxShadow: '0 10px 25px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: '18px' }}>공고 삭제</h3>
            <p style={{ margin: '0 0 24px', color: 'var(--muted)', fontSize: '14px', lineHeight: 1.6 }}>
              <strong>"{notice.title}"</strong> 공고를 정말 삭제하시겠습니까?<br/>삭제된 데이터는 복구할 수 없습니다.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button className="btn btn-outline" onClick={() => setDeleteConfirm(false)} disabled={isDeleting}>취소</button>
              <button className="btn btn-danger" onClick={handleDelete} disabled={isDeleting}>
                {isDeleting ? '삭제 중...' : '삭제하기'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
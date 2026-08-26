import { useState, useEffect } from 'react';
// 💡 프로젝트 환경에 맞게 API_BASE_URL 또는 api helper를 import 하세요.
// import { API_BASE_URL } from '../../config'; 
const API_BASE_URL = '/api'; // 임시 설정 (실제 환경에 맞게 수정)

export interface GlossaryItem {
  id: number;
  term: string;
  definition: string;
  category: string;
  is_active: boolean;
}

const PAGE_SIZE = 5;

export default function GlossaryAdmin() {
  const [terms, setTerms] = useState<GlossaryItem[]>([]);
  
  // 검색, 필터, 페이징 State
  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // 모달 및 폼 State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<GlossaryItem | null>(null);
  const [formData, setFormData] = useState({ term: '', definition: '', category: '', is_active: true });

  // 토스트 알림 State
  const [toast, setToast] = useState<{ message: string; id: number } | null>(null);
  const showToast = (message: string) => {
    const id = Date.now();
    setToast({ message, id });
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 2500);
  };

  // 💡 [GET] 목록 조회 (서버 페이지네이션 적용)
  const fetchTerms = async () => {
    try {
      const params = new URLSearchParams({
        page: String(page),
        size: String(PAGE_SIZE)
      });
      if (keyword) params.set('search', keyword);
      if (categoryFilter) params.set('category', categoryFilter);
      if (statusFilter !== '') params.set('is_active', statusFilter);

      // 인증 토큰이 필요하다면 headers에 Authorization을 추가해야 합니다.
      const res = await fetch(`${API_BASE_URL}/admin/glossary?${params.toString()}`, {
        headers: {
          'Content-Type': 'application/json',
          // 'Authorization': `Bearer ${localStorage.getItem('admin_token')}` // 필요 시 주석 해제
        }
      });

      if (!res.ok) throw new Error('데이터를 불러오는데 실패했습니다.');
      
      const data = await res.json();
      setTerms(data.items || []); // 배열 대신 data.items 로 접근
      setTotalPages(data.total_pages || 1);
      setTotalCount(data.total || 0);
    } catch (error) {
      console.error(error);
      showToast('목록을 불러오는 중 오류가 발생했습니다.');
    }
  };

  // 페이지나 필터가 바뀔 때마다 fetchTerms 실행
  useEffect(() => {
    fetchTerms();
  }, [page, keyword, categoryFilter, statusFilter]);

  const openModal = (item?: GlossaryItem) => {
    if (item) {
      setEditingItem(item);
      setFormData({ term: item.term, definition: item.definition, category: item.category, is_active: item.is_active });
    } else {
      setEditingItem(null);
      setFormData({ term: '', definition: '', category: '청약/자격', is_active: true });
    }
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingItem(null);
  };

  // 💡 [POST / PUT] 신규 추가 및 수정
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.term || !formData.definition) {
      showToast('용어와 설명을 모두 입력해주세요.');
      return;
    }

    try {
      const url = editingItem 
        ? `${API_BASE_URL}/admin/glossary/${editingItem.id}` 
        : `${API_BASE_URL}/admin/glossary`;
      
      const method = editingItem ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });

      if (res.status === 409) {
        showToast('이미 등록된 동일한 용어가 있습니다.');
        return;
      }
      if (!res.ok) throw new Error('저장 실패');

      showToast(editingItem ? '용어가 수정되었습니다.' : '새 용어가 추가되었습니다.');
      closeModal();
      setPage(1); // 저장 후 1페이지로 리프레시
      fetchTerms();
    } catch (error) {
      console.error(error);
      showToast('저장 중 오류가 발생했습니다.');
    }
  };

  // 💡 [DELETE] 용어 삭제
  const handleDelete = async (id: number) => {
    if (window.confirm('정말로 이 용어를 삭제하시겠습니까?')) {
      try {
        const res = await fetch(`${API_BASE_URL}/admin/glossary/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('삭제 실패');
        
        showToast('용어가 삭제되었습니다.');
        fetchTerms();
      } catch (error) {
        console.error(error);
        showToast('삭제 중 오류가 발생했습니다.');
      }
    }
  };

  // 💡 [PATCH] 상태(ON/OFF) 변경
  const toggleStatus = async (id: number, currentStatus: boolean) => {
    try {
      const newStatus = !currentStatus;
      const res = await fetch(`${API_BASE_URL}/admin/glossary/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: newStatus })
      });

      if (!res.ok) throw new Error('상태 변경 실패');

      showToast(`상태가 ${newStatus ? 'ON' : 'OFF'}로 변경되었습니다.`);
      fetchTerms(); // 상태 변경 후 목록 새로고침
    } catch (error) {
      console.error(error);
      showToast('상태 변경 중 오류가 발생했습니다.');
    }
  };

  return (
    <main className="content relative">
      {/* 토스트 메시지 */}
      {toast && (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[9999] bg-slate-800 text-white px-6 py-3 rounded-xl shadow-2xl text-[14px] font-bold flex items-center gap-2 animate-[fadeIn_0.2s_ease-out]">
          <span>🔔</span> {toast.message}
        </div>
      )}

      <div className="page-head">
        <div>
          <h1>용어 사전 관리</h1>
          <p>사용자 챗봇 화면에서 툴팁으로 제공될 어려운 청약 용어들을 관리합니다.</p>
        </div>
        <button className="btn btn-primary" onClick={() => openModal()}>＋ 용어 추가</button>
      </div>

      <section className="stats">
        <div className="card stat"><small>전체 등록 용어</small><strong>{totalCount}</strong></div>
      </section>
      
      <section className="card filters" style={{ gridTemplateColumns: 'minmax(240px, 1fr) repeat(2, 1fr) auto' }}>
        <input 
          className="input wide" 
          placeholder="용어 또는 설명 검색" 
          value={keyword} 
          onChange={(e) => { setKeyword(e.target.value); setPage(1); }} 
          onKeyDown={(e) => e.key === 'Enter' && fetchTerms()}
        />
        <select className="select" value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}>
          <option value="">카테고리 전체</option>
          <option value="청약/자격">청약/자격</option>
          <option value="소득/자산">소득/자산</option>
          <option value="주택/면적">주택/면적</option>
          <option value="주택/유형">주택/유형</option>
          <option value="청약/당첨">청약/당첨</option>
        </select>
        <select className="select" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}>
          <option value="">활성화 상태 전체</option>
          <option value="true">사용 중 (ON)</option>
          <option value="false">미사용 (OFF)</option>
        </select>
        <button className="btn btn-primary" onClick={() => fetchTerms()}>검색</button>
      </section>

      <section className="card table-card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '70px', textAlign: 'center' }}>ID</th>
                <th style={{ width: '130px' }}>카테고리</th>
                <th style={{ width: '160px' }}>용어</th>
                <th>설명 (툴팁 내용)</th>
                <th style={{ width: '100px', textAlign: 'center' }}>상태</th>
                <th style={{ width: '140px', textAlign: 'center' }}>작업</th>
              </tr>
            </thead>
            <tbody>
              {terms.length > 0 ? (
                terms.map((t) => (
                  <tr key={t.id}>
                    <td style={{ textAlign: 'center' }}>{t.id}</td>
                    <td>{t.category}</td>
                    <td className="title-cell" style={{ fontWeight: 700 }}>{t.term}</td>
                    <td style={{ maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.definition}</td>
                    <td style={{ textAlign: 'center' }}>
                      <button 
                        className={`badge ${t.is_active ? 'green' : 'gray'}`} 
                        style={{ cursor: 'pointer', border: 'none', width: '60px' }}
                        onClick={() => toggleStatus(t.id, t.is_active)}
                      >
                        {t.is_active ? 'ON' : 'OFF'}
                      </button>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <div style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
                        <button className="btn btn-outline" style={{ height: '30px', padding: '0 10px', fontSize: '12px' }} onClick={() => openModal(t)}>수정</button>
                        <button className="btn btn-outline" style={{ height: '30px', padding: '0 10px', fontSize: '12px', color: '#ef4444', borderColor: '#fca5a5' }} onClick={() => handleDelete(t.id)}>삭제</button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={6} className="empty">검색 결과가 없습니다.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        
        {totalPages > 1 && (
          <div className="pagination">
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
              <button key={p} className={page === p ? "active" : ""} onClick={() => setPage(p)}>
                {p}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* 모달 유지 */}
      {isModalOpen && (
        <div className="mobile-overlay show" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
          <div className="card" style={{ width: '100%', maxWidth: '500px', margin: '20px', padding: '32px' }}>
            <h2 style={{ fontSize: '22px', fontWeight: 800, marginBottom: '24px', color: 'var(--text)' }}>
              {editingItem ? '용어 수정' : '신규 용어 추가'}
            </h2>
            
            <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 700, marginBottom: '8px' }}>카테고리</label>
                <select className="select wide" value={formData.category} onChange={(e) => setFormData({...formData, category: e.target.value})}>
                  <option value="청약/자격">청약/자격</option>
                  <option value="소득/자산">소득/자산</option>
                  <option value="주택/면적">주택/면적</option>
                  <option value="주택/유형">주택/유형</option>
                  <option value="청약/당첨">청약/당첨</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 700, marginBottom: '8px' }}>용어 (단어)</label>
                <input required className="input wide" value={formData.term} onChange={(e) => setFormData({...formData, term: e.target.value})} />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 700, marginBottom: '8px' }}>설명</label>
                <textarea required className="input wide" value={formData.definition} onChange={(e) => setFormData({...formData, definition: e.target.value})} style={{ minHeight: '120px' }} />
              </div>

              <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
                <button type="button" className="btn btn-outline" style={{ flex: 1, padding: '12px' }} onClick={closeModal}>취소</button>
                <button type="submit" className="btn btn-primary" style={{ flex: 1, padding: '12px' }}>{editingItem ? '수정 내용 저장' : '등록하기'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
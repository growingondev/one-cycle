import { useState, useMemo } from 'react';

export interface GlossaryItem {
  id: number;
  term: string;
  definition: string;
  category: string;
  is_active: boolean;
}

// 💡 페이지네이션 테스트를 위해 더미 데이터를 조금 더 늘렸습니다.
const initialDummyData: GlossaryItem[] = [
  { id: 1, term: '무주택세대구성원', definition: '세대원 전원이 주택을 소유하고 있지 않은 세대의 구성원입니다.', category: '청약/자격', is_active: true },
  { id: 2, term: '기준중위소득', definition: '보건복지부장관이 고시하는 국민 전체 가구 소득의 중간값입니다.', category: '소득/자산', is_active: true },
  { id: 3, term: '전용면적', definition: '아파트 등 공동주택에서 실제 주거에 사용되는 내부 면적입니다.', category: '주택/면적', is_active: true },
  { id: 4, term: '행복주택', definition: '청년, 신혼부부 등을 위해 직장/학교가 가까운 곳에 저렴하게 공급하는 임대주택입니다.', category: '주택/유형', is_active: false },
  { id: 5, term: '가점제', definition: '무주택기간, 부양가족 수 등을 점수로 계산해 점수가 높은 순으로 선정하는 방식입니다.', category: '청약/당첨', is_active: true },
  { id: 6, term: '국민임대', definition: '무주택 저소득층의 주거안정을 위해 최장 30년간 임대하는 주택입니다.', category: '주택/유형', is_active: true },
  { id: 7, term: '총자산', definition: '부동산, 자동차, 금융자산, 일반자산을 모두 합산한 후 부채를 차감한 자산입니다.', category: '소득/자산', is_active: true },
];

const PAGE_SIZE = 5; // 한 페이지에 보여줄 개수

export default function GlossaryAdmin() {
  const [terms, setTerms] = useState<GlossaryItem[]>(initialDummyData);
  
  // 검색 및 필터 State
  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<GlossaryItem | null>(null);
  const [formData, setFormData] = useState({ term: '', definition: '', category: '', is_active: true });

  // 💡 토스트(Toast) 알림 State
  const [toast, setToast] = useState<{ message: string; id: number } | null>(null);
  const showToast = (message: string) => {
    const id = Date.now();
    setToast({ message, id });
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 2500);
  };

  // 💡 필터링, 통계, 페이지네이션 계산 로직
  const { paginatedTerms, totalPages, stats } = useMemo(() => {
    let filtered = terms;
    if (keyword) {
      filtered = filtered.filter(t => t.term.includes(keyword) || t.definition.includes(keyword));
    }
    if (categoryFilter) {
      filtered = filtered.filter(t => t.category === categoryFilter);
    }
    if (statusFilter !== '') {
      const isActive = statusFilter === 'true';
      filtered = filtered.filter(t => t.is_active === isActive);
    }

    // 페이지네이션 계산
    const totalPagesCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    // 현재 페이지가 전체 페이지보다 크면 1페이지로 조정
    const currentPage = page > totalPagesCount ? 1 : page; 
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    const paginated = filtered.slice(startIndex, startIndex + PAGE_SIZE);

    return {
      paginatedTerms: paginated,
      totalPages: totalPagesCount,
      stats: {
        total: terms.length,
        filteredTotal: filtered.length,
        active: terms.filter(t => t.is_active).length,
        inactive: terms.filter(t => !t.is_active).length,
      }
    };
  }, [terms, keyword, categoryFilter, statusFilter, page]);

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

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.term || !formData.definition) {
      showToast('용어와 설명을 모두 입력해주세요.');
      return;
    }

    if (editingItem) {
      setTerms(terms.map(t => t.id === editingItem.id ? { ...t, ...formData } : t));
      showToast('용어가 성공적으로 수정되었습니다.');
    } else {
      const newItem = { id: Date.now(), ...formData };
      setTerms([newItem, ...terms]);
      setPage(1); // 새 용어 추가 시 1페이지로 이동
      showToast('새로운 용어가 추가되었습니다.');
    }
    closeModal();
  };

  const handleDelete = (id: number) => {
    if (window.confirm('정말로 이 용어를 삭제하시겠습니까?')) {
      setTerms(terms.filter(t => t.id !== id));
      showToast('용어가 삭제되었습니다.');
    }
  };

  const toggleStatus = (id: number, currentStatus: boolean) => {
    setTerms(terms.map(t => t.id === id ? { ...t, is_active: !t.is_active } : t));
    showToast(`상태가 ${currentStatus ? 'OFF' : 'ON'}로 변경되었습니다.`);
  };

  return (
    <main className="content relative">
      {/* 💡 토스트 메시지 UI */}
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
        <div className="card stat"><small>전체 등록 용어</small><strong>{stats.total}</strong></div>
        <div className="card stat"><small>사용 중 (ON)</small><strong style={{ color: 'var(--green)' }}>{stats.active}</strong></div>
        <div className="card stat"><small>미사용 (OFF)</small><strong style={{ color: 'var(--muted)' }}>{stats.inactive}</strong></div>
      </section>
      
      <section className="card filters" style={{ gridTemplateColumns: 'minmax(240px, 1fr) repeat(2, 1fr) auto' }}>
        <input 
          className="input wide" 
          placeholder="용어 또는 설명 검색" 
          value={keyword} 
          onChange={(e) => { setKeyword(e.target.value); setPage(1); }} 
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
        <button className="btn btn-primary" onClick={() => setPage(1)}>검색</button>
      </section>

      <section className="card table-card">
        <div className="table-toolbar">
          <b>검색 결과 {stats.filteredTotal}건</b>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '70px', textAlign: 'center' }}>ID</th>
                <th style={{ width: '130px' }}>카테고리</th>
                <th style={{ width: '160px' }}>용어</th>
                <th>설명 (툴팁 내용)</th>
                <th style={{ width: '100px', textAlign: 'center' }}>활성화 상태</th>
                <th style={{ width: '140px', textAlign: 'center' }}>작업</th>
              </tr>
            </thead>
            <tbody>
              {paginatedTerms.length > 0 ? (
                paginatedTerms.map((t) => (
                  <tr key={t.id}>
                    <td style={{ textAlign: 'center' }}>{t.id}</td>
                    <td>{t.category}</td>
                    <td className="title-cell" style={{ fontWeight: 700 }}>{t.term}</td>
                    <td style={{ maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {t.definition}
                    </td>
                    <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                      <button 
                        className={`badge ${t.is_active ? 'green' : 'gray'}`} 
                        style={{ cursor: 'pointer', border: 'none', width: '60px' }}
                        onClick={() => toggleStatus(t.id, t.is_active)}
                        title="클릭하여 상태 변경"
                      >
                        {t.is_active ? 'ON' : 'OFF'}
                      </button>
                    </td>
                    <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
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
        
        {/* 💡 페이지네이션 UI */}
        {totalPages > 1 && (
          <div className="pagination">
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
              <button 
                key={p} 
                className={page === p ? "active" : ""} 
                onClick={() => setPage(p)}
              >
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
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 700, marginBottom: '8px', color: 'var(--muted)' }}>카테고리 분류</label>
                <select className="select wide" value={formData.category} onChange={(e) => setFormData({...formData, category: e.target.value})}>
                  <option value="청약/자격">청약/자격</option>
                  <option value="소득/자산">소득/자산</option>
                  <option value="주택/면적">주택/면적</option>
                  <option value="주택/유형">주택/유형</option>
                  <option value="청약/당첨">청약/당첨</option>
                  <option value="비용/계약">비용/계약</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 700, marginBottom: '8px', color: 'var(--muted)' }}>용어 (단어)</label>
                <input required className="input wide" placeholder="예: 무주택세대구성원" value={formData.term} onChange={(e) => setFormData({...formData, term: e.target.value})} />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 700, marginBottom: '8px', color: 'var(--muted)' }}>용어 설명 (툴팁 내용)</label>
                <textarea required className="input wide" placeholder="용어에 대한 쉬운 설명을 입력하세요." value={formData.definition} onChange={(e) => setFormData({...formData, definition: e.target.value})} style={{ minHeight: '120px', resize: 'vertical', lineHeight: '1.5' }} />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', padding: '12px', background: '#f8f9fc', borderRadius: '8px' }}>
                <input type="checkbox" id="isActiveCheck" checked={formData.is_active} onChange={(e) => setFormData({...formData, is_active: e.target.checked})} style={{ width: '18px', height: '18px' }} />
                <label htmlFor="isActiveCheck" style={{ fontSize: '14px', fontWeight: 600, cursor: 'pointer', color: 'var(--text)' }}>
                  활성화 (체크 시 사용자 화면 챗봇 툴팁에 즉시 노출됩니다)
                </label>
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
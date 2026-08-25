import { useState, useMemo } from 'react';

export interface GlossaryItem {
  id: number;
  term: string;
  definition: string;
  category: string;
  is_active: boolean;
}

// 💡 초기 더미 데이터 (40개 중 일부를 테스트용으로 배치)
const initialDummyData: GlossaryItem[] = [
  { id: 1, term: '무주택세대구성원', definition: '세대원 전원이 주택을 소유하고 있지 않은 세대의 구성원입니다.', category: '청약/자격', is_active: true },
  { id: 2, term: '기준중위소득', definition: '보건복지부장관이 고시하는 국민 전체 가구 소득의 중간값입니다.', category: '소득/자산', is_active: true },
  { id: 3, term: '전용면적', definition: '아파트 등 공동주택에서 실제 주거에 사용되는 내부 면적입니다.', category: '주택/면적', is_active: true },
  { id: 4, term: '행복주택', definition: '청년, 신혼부부 등을 위해 직장/학교가 가까운 곳에 저렴하게 공급하는 임대주택입니다.', category: '주택/유형', is_active: false },
  { id: 5, term: '가점제', definition: '무주택기간, 부양가족 수 등을 점수로 계산해 점수가 높은 순으로 선정하는 방식입니다.', category: '청약/당첨', is_active: true },
];

export default function GlossaryAdmin() {
  const [terms, setTerms] = useState<GlossaryItem[]>(initialDummyData);
  
  // 검색 및 필터 State
  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  
  // 페이징 State (MVP에서는 1페이지만 유지)
  const [page, setPage] = useState(1);

  // 모달 제어용 State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<GlossaryItem | null>(null);
  const [formData, setFormData] = useState({ term: '', definition: '', category: '', is_active: true });

  // 💡 필터링 및 통계 계산 로직
  const { filteredTerms, stats } = useMemo(() => {
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

    return {
      filteredTerms: filtered,
      stats: {
        total: terms.length,
        active: terms.filter(t => t.is_active).length,
        inactive: terms.filter(t => !t.is_active).length,
      }
    };
  }, [terms, keyword, categoryFilter, statusFilter]);

  // 모달 열기
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
      alert('용어와 설명을 모두 입력해주세요.');
      return;
    }

    if (editingItem) {
      setTerms(terms.map(t => t.id === editingItem.id ? { ...t, ...formData } : t));
    } else {
      const newItem = { id: Date.now(), ...formData };
      setTerms([newItem, ...terms]);
    }
    closeModal();
  };

  const handleDelete = (id: number) => {
    if (window.confirm('정말로 이 용어를 삭제하시겠습니까?')) {
      setTerms(terms.filter(t => t.id !== id));
    }
  };

  const toggleStatus = (id: number) => {
    setTerms(terms.map(t => t.id === id ? { ...t, is_active: !t.is_active } : t));
  };

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>용어 사전 관리</h1>
          <p>사용자 챗봇 화면에서 툴팁으로 제공될 어려운 청약 용어들을 관리합니다.</p>
        </div>
        <button className="btn btn-primary" onClick={() => openModal()}>＋ 용어 추가</button>
      </div>

      {/* 💡 기존 디자인을 활용한 상단 통계 위젯 */}
      <section className="stats">
        <div className="card stat"><small>전체 등록 용어</small><strong>{stats.total}</strong></div>
        <div className="card stat"><small>사용 중 (ON)</small><strong style={{ color: 'var(--green)' }}>{stats.active}</strong></div>
        <div className="card stat"><small>미사용 (OFF)</small><strong style={{ color: 'var(--muted)' }}>{stats.inactive}</strong></div>
      </section>
      
      {/* 💡 검색 및 필터 영역 */}
      <section className="card filters" style={{ gridTemplateColumns: 'minmax(240px, 1fr) repeat(2, 1fr) auto' }}>
        <input 
          className="input wide" 
          placeholder="용어 또는 설명 검색" 
          value={keyword} 
          onChange={(e) => setKeyword(e.target.value)} 
        />
        <select className="select" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
          <option value="">카테고리 전체</option>
          <option value="청약/자격">청약/자격</option>
          <option value="소득/자산">소득/자산</option>
          <option value="주택/면적">주택/면적</option>
          <option value="주택/유형">주택/유형</option>
          <option value="청약/당첨">청약/당첨</option>
        </select>
        <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">활성화 상태 전체</option>
          <option value="true">사용 중 (ON)</option>
          <option value="false">미사용 (OFF)</option>
        </select>
        <button className="btn btn-primary" onClick={() => setPage(1)}>검색</button>
      </section>

      {/* 💡 테이블 영역 */}
      <section className="card table-card">
        <div className="table-toolbar">
          <b>검색 결과 {filteredTerms.length}건</b>
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
              {filteredTerms.length > 0 ? (
                filteredTerms.map((t) => (
                  <tr key={t.id}>
                    <td style={{ textAlign: 'center' }}>{t.id}</td>
                    <td>{t.category}</td>
                    <td className="title-cell" style={{ fontWeight: 700 }}>{t.term}</td>
                    <td style={{ maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {t.definition}
                    </td>
                    <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                      {/* 상태 토글 버튼 (뱃지 스타일 활용) */}
                      <button 
                        className={`badge ${t.is_active ? 'green' : 'gray'}`} 
                        style={{ cursor: 'pointer', border: 'none', width: '60px' }}
                        onClick={() => toggleStatus(t.id)}
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
        <div className="pagination">
          <button className="active">1</button>
        </div>
      </section>

      {/* 💡 신규 추가 / 수정 모달 */}
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
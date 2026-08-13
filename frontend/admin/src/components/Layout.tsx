// src/components/Layout.tsx
import { useState, useEffect } from 'react';
import { Outlet, useNavigate, NavLink, useLocation } from 'react-router-dom';

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // 페이지(라우트)가 변경될 때마다 모바일 메뉴를 닫습니다.
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  // 로그아웃 버튼 동작[cite: 22]
  const handleLogout = () => {
    sessionStorage.removeItem('mock_token');
    navigate('/');
  };

  return (
    <div className="admin-shell">
      
      {/* 1. 사이드바 영역 (sidebar.html 구조)[cite: 22] */}
      {/* isMobileMenuOpen 상태가 true면 'open' 클래스가 추가되어 화면에 나타납니다.[cite: 21] */}
      <aside className={`sidebar ${isMobileMenuOpen ? 'open' : ''}`} id="sidebar">
        <div className="brand">
          <span className="brand-mark">LH</span>
          <span>공고 관리자</span>
        </div>
        
        <nav className="nav">
          {/* NavLink는 현재 URL과 일치하면 자동으로 active 클래스를 붙여줍니다.[cite: 21, 22] */}
          <NavLink to="/announcement" className={({ isActive }) => isActive ? 'active' : ''}>
            ▤ &nbsp;공고 관리
          </NavLink>
          <NavLink to="/document" className={({ isActive }) => isActive ? 'active' : ''}>
            ▧ &nbsp;문서 관리
          </NavLink>
          <NavLink to="/error" className={({ isActive }) => isActive ? 'active' : ''}>
            △ &nbsp;오류 관리
          </NavLink>
        </nav>

        <div className="sidebar-user">
          <div className="user-row">
            <span className="avatar">관</span>
            <div>
              <b>관리자</b>
              <div style={{ fontSize: '12px', color: '#91a1ba' }}>admin</div>
            </div>
          </div>
          <button className="logout" onClick={handleLogout}>로그아웃</button>
        </div>
      </aside>

      {/* 2. 모바일 오버레이 배경[cite: 22] */}
      {/* 바깥 어두운 배경을 누르면 메뉴가 닫히도록 onClick 이벤트를 설정했습니다. */}
      <div 
        className={`mobile-overlay ${isMobileMenuOpen ? 'show' : ''}`} 
        id="overlay" 
        onClick={() => setIsMobileMenuOpen(false)}
      ></div>

      {/* 3. 메인 영역 */}
      <div className="main">
        {/* 상단 헤더 (header.html 구조)[cite: 23] */}
        <header className="topbar">
          <button 
            className="icon-btn mobile-menu" 
            id="menuBtn" 
            aria-label="메뉴"
            onClick={() => setIsMobileMenuOpen(true)}
          >
            ☰
          </button>
          <div style={{ fontSize: '13px', color: '#718095' }}>
            LH 공고 AI 도우미 <span>관리자</span> 시스템
          </div>
        </header>

        {/* 하단 페이지 내용 (공고관리, 문서관리 등이 렌더링될 자리) */}
        <Outlet />
      </div>

    </div>
  );
}
import { useState, useEffect } from 'react';
import { Outlet, useNavigate, NavLink, useLocation } from 'react-router-dom';

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  // 페이지 진입 시 로그인 상태 검증
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch('/api/admin/auth/me', {
          credentials: 'include',
        });
        if (res.status === 401 || !res.ok) {
          navigate('/');
        }
      } catch {
        navigate('/');
      }
    };
    checkAuth();
  }, [navigate, location.pathname]);

  const handleLogout = async () => {
    try {
      await fetch('/api/admin/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
    } catch (e) {
      console.error('로그아웃 요청 실패', e);
    } finally {
      navigate('/');
    }
  };

  return (
    <div className="admin-shell">
      <aside className={`sidebar ${isMobileMenuOpen ? 'open' : ''}`} id="sidebar">
        <div className="brand">
          <span className="brand-mark">LH</span>
          <span>공고 관리자</span>
        </div>
        
        <nav className="nav">
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

      <div 
        className={`mobile-overlay ${isMobileMenuOpen ? 'show' : ''}`} 
        id="overlay" 
        onClick={() => setIsMobileMenuOpen(false)}
      ></div>

      <div className="main">
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

        <Outlet />
      </div>
    </div>
  );
}
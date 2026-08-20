// src/pages/Login.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../assets/css/login.css';

export default function Login() {
  const navigate = useNavigate();
  const [adminId, setAdminId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault(); 
    
    // README 명세서 기준 테스트 계정 검증
    if (adminId === 'admin' && password === 'admin1234') {
      // 성공 시 세션 스토리지에 Mock JWT 저장 후 이동
      sessionStorage.setItem('mock_token', 'Header.Payload.MockSignature');
      navigate('/announcement');
    } else {
      // 실패 시 에러 메시지 출력
      setErrorMsg('아이디 또는 비밀번호가 올바르지 않습니다.');
    }
  };

  return (
    <main className="login-page">
      <section className="login-visual">
        <div className="visual-inner">
          <div className="visual-logo">
            <span>LH</span>
            <span>공고 AI 도우미</span>
          </div>
          <h1>관리자 시스템에<br />로그인하세요.</h1>
          <p>공고 수집, 문서 처리 및 오류 현황을 한곳에서 안전하게 관리할 수 있습니다.</p>
        </div>
      </section>

      <section className="login-area">
        <div className="login-box">
          <h2>관리자 로그인</h2>
          <p>관리자 계정으로 로그인해 주세요.</p>

          <form id="loginForm" onSubmit={handleLogin}>
            <div className="field">
              <label htmlFor="adminId">아이디</label>
              <input
                className="input login-input"
                id="adminId"
                name="adminId"
                autoComplete="username"
                placeholder="아이디를 입력하세요"
                value={adminId}
                onChange={(e) => setAdminId(e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="password">비밀번호</label>
              <div className="password-wrap">
                <input
                  className="input login-input"
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="비밀번호를 입력하세요"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  id="togglePassword"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? "숨기기" : "보기"}
                </button>
              </div>
            </div>

            <div className="login-error" id="loginError">
              {errorMsg}
            </div>

            <button type="submit" className="btn btn-primary login-submit" id="loginButton">
              로그인
            </button>
          </form>

          <div className="login-help">
            <b>시연용 계정</b><br />
            아이디: admin / 비밀번호: admin1234<br />
            실제 서비스에서는 FastAPI 인증 API로 교체해야 합니다.
          </div>
        </div>
      </section>
    </main>
  );
}
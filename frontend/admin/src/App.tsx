// src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import Layout from './components/Layout';
import Announcement from './pages/Announcement';
import Document from './pages/Document';
import ErrorPage from './pages/Error';  
import GlossaryAdmin from './pages/GlossaryAdmin';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        
        {/* Layout이 적용되는(사이드바가 있는) 페이지들 */}
        <Route element={<Layout />}>
          <Route path="/announcement" element={<Announcement />} />
          <Route path="/document" element={<Document />} />
          <Route path="/error" element={<ErrorPage />} />
          
          {/* ✅ 여기에 용어 사전 관리 페이지 경로를 추가했습니다! */}
          <Route path="/glossary" element={<GlossaryAdmin />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
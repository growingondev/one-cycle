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
        
        <Route element={<Layout />}>
          <Route path="/announcement" element={<Announcement />} />
          <Route path="/document" element={<Document />} />
          <Route path="/error" element={<ErrorPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
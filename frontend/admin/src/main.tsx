// src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './assets/css/common.css' 
import './assets/css/layout.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
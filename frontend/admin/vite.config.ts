import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000, // 포트를 3000번으로 고정
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18000', // 기존 FastAPI 서버 주소
        changeOrigin: true,
      }
    }
  }
})
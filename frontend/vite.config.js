import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 백엔드는 :8000, 접두사 없이 /session/advise 등을 그대로 노출한다 (docs/CONTRACTS.md 기준).
// 백엔드가 꺼져 있으면 src/api/client.js가 자동으로 목업 데이터로 폴백한다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // 기본값 'assets'는 nginx의 API 프록시 경로(/assets -> backend)와 충돌한다.
    // 빌드 산출물 폴더 이름만 바꿔서 경로 충돌을 피한다.
    assetsDir: 'static-files',
  },
  server: {
    port: 5173,
    proxy: {
      '/session': 'http://localhost:8000',
      '/catalog': 'http://localhost:8000',
      '/customers': 'http://localhost:8000',
      '/sessions': 'http://localhost:8000',
      '/demo': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
      // 자유 상담(/chat)이 직접 부르는 계약 엔드포인트.
      '/assets': 'http://localhost:8000',
      '/intent': 'http://localhost:8000',
      // 개체 식별 화면(/fingerprint 페이지)이 부르는 매칭 엔드포인트
      '/fingerprint': 'http://localhost:8000',
      '/clienteling': 'http://localhost:8000',
    },
  },
})

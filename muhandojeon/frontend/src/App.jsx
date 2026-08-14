import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import ProductScreen from './pages/ProductScreen.jsx'
import CaptureScreen from './pages/CaptureScreen.jsx'
import ChatScreen from './pages/ChatScreen.jsx'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* 제품 상세 + 컨디션 화면 (기본 진입점) */}
        <Route path="/" element={<ProductScreen />} />
        <Route path="/product/:productId" element={<ProductScreen />} />

        {/* 제품 지문 등록 — 촬영 UI */}
        <Route path="/capture" element={<CaptureScreen />} />
        <Route path="/capture/:productId" element={<CaptureScreen />} />

        {/* AI 클라이언텔링 상담 화면 */}
        <Route path="/chat/:productId" element={<ChatScreen />} />
      </Route>
    </Routes>
  )
}

export default App

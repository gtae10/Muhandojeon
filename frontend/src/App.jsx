import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import ScenarioScreen from './pages/ScenarioScreen.jsx'
import ConsultScreen from './pages/ConsultScreen.jsx'
import AdviseResultScreen from './pages/AdviseResultScreen.jsx'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* 발표용 고정 시나리오 재생 — 기본 진입점 */}
        <Route path="/" element={<ScenarioScreen />} />

        {/* 임의 고객 + 상품으로 직접 상담 호출 */}
        <Route path="/consult" element={<ConsultScreen />} />

        {/* AdviseResponse 렌더링 — 공통 결과 화면 */}
        <Route path="/result" element={<AdviseResultScreen />} />
      </Route>
    </Routes>
  )
}

export default App

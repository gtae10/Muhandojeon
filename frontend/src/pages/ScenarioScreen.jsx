import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDemoScenarios, runDemoScenario } from '../api/client.js'

export default function ScenarioScreen() {
  const navigate = useNavigate()
  const [scenarios, setScenarios] = useState([])
  const [status, setStatus] = useState('loading') // loading | ready
  const [runningId, setRunningId] = useState(null)

  useEffect(() => {
    getDemoScenarios().then((data) => {
      setScenarios(data.items ?? [])
      setStatus('ready')
    })
  }, [])

  async function handleRun(scenarioId) {
    setRunningId(scenarioId)
    const result = await runDemoScenario(scenarioId)
    navigate('/result', { state: { advise: result.response, scenario: result.scenario } })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-medium">데모 시나리오</h1>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          고정된 고객·상품·세션으로 상담을 재생해요
        </p>
      </div>

      {status === 'loading' && (
        <p className="text-sm text-[var(--color-muted)]">불러오는 중…</p>
      )}

      <div className="space-y-3">
        {scenarios.map((s) => (
          <div
            key={s.id}
            className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
          >
            <span className="text-xs font-mono text-[var(--color-accent)]">{s.id}</span>
            <p className="text-sm font-medium mt-1">{s.title}</p>
            <p className="text-xs text-[var(--color-muted)] mt-2 leading-relaxed">
              {s.narrative}
            </p>
            <button
              onClick={() => handleRun(s.id)}
              disabled={runningId === s.id}
              className="w-full mt-4 py-2.5 rounded-full bg-[var(--color-accent)] text-black text-sm disabled:opacity-50"
            >
              {runningId === s.id ? '상담 생성 중…' : '이 시나리오 재생'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

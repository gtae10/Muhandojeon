import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDemoScenarios, runDemoScenario, ApiError } from '../api/client.js'
import { CardSkeleton } from '../components/Skeleton.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ScenarioScreen() {
  const navigate = useNavigate()
  const [scenarios, setScenarios] = useState([])
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [loadError, setLoadError] = useState(null)
  const [runningId, setRunningId] = useState(null)
  const [runError, setRunError] = useState(null) // { scenarioId, message }

  function load() {
    setStatus('loading')
    setLoadError(null)
    getDemoScenarios()
      .then((data) => {
        setScenarios(data.items ?? [])
        setStatus('ready')
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : '시나리오를 불러오지 못했어요')
        setStatus('error')
      })
  }

  useEffect(() => {
    load()
  }, [])

  async function handleRun(scenarioId) {
    setRunningId(scenarioId)
    setRunError(null)
    try {
      const result = await runDemoScenario(scenarioId)
      navigate('/result', { state: { advise: result.response, scenario: result.scenario } })
    } catch (err) {
      setRunError({
        scenarioId,
        message: err instanceof ApiError ? err.message : '시나리오 실행에 실패했어요',
      })
    } finally {
      setRunningId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-medium">데모 시나리오</h1>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          고정된 고객·상품·세션으로 상담을 재생해요
        </p>
      </div>

      {status === 'loading' && <CardSkeleton count={3} />}

      {status === 'error' && <ErrorBanner message={loadError} onRetry={load} />}

      {status === 'ready' && (
        <div className="space-y-3">
          {scenarios.map((s) => (
            <div
              key={s.id}
              className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-colors duration-150 hover:border-[var(--color-accent)]/30 hover:bg-[var(--color-surface-raised)]"
            >
              <span className="text-xs font-mono text-[var(--color-accent)]">{s.id}</span>
              <p className="text-sm font-medium mt-1">{s.title}</p>
              <p className="text-xs text-[var(--color-muted)] mt-2 leading-relaxed">
                {s.narrative}
              </p>

              {runError?.scenarioId === s.id && (
                <div className="mt-3">
                  <ErrorBanner message={runError.message} onRetry={() => handleRun(s.id)} />
                </div>
              )}

              <button
                onClick={() => handleRun(s.id)}
                disabled={runningId === s.id}
                className="w-full mt-4 py-2.5 rounded-full bg-[var(--color-accent)] text-black text-sm transition-opacity duration-150 hover:opacity-90 disabled:opacity-50 disabled:hover:opacity-50"
              >
                {runningId === s.id ? '상담 생성 중…' : '이 시나리오 재생'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

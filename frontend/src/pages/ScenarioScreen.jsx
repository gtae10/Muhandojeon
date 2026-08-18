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
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-xl text-[var(--color-text)]">데모 시나리오</h1>
        <p className="text-xs text-[var(--color-muted)] mt-2">
          고정된 고객·상품·세션으로 상담을 재생해요
        </p>
      </div>

      {status === 'loading' && <CardSkeleton count={3} />}

      {status === 'error' && <ErrorBanner message={loadError} onRetry={load} />}

      {status === 'ready' && (
        <div className="divide-y divide-[var(--color-border)]">
          {scenarios.map((s) => (
            <div key={s.id} className="py-7 first:pt-0 last:pb-0">
              <span className="text-[10px] tracking-[0.14em] text-[var(--color-accent)]">{s.id}</span>
              <p className="font-display text-[17px] mt-2 text-[var(--color-text)]">{s.title}</p>
              <p className="text-xs text-[var(--color-muted)] mt-2.5 leading-relaxed">{s.narrative}</p>

              {runError?.scenarioId === s.id && (
                <div className="mt-4">
                  <ErrorBanner message={runError.message} onRetry={() => handleRun(s.id)} />
                </div>
              )}

              <button
                onClick={() => handleRun(s.id)}
                disabled={runningId === s.id}
                className="w-full mt-5 py-3 border border-[var(--color-accent)] text-[var(--color-accent)] text-[11px] tracking-[0.14em] uppercase transition-colors duration-150 hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-[var(--color-accent)]"
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

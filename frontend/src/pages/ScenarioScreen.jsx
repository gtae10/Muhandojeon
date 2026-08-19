import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDemoScenarios, runDemoScenario, ApiError } from '../api/client.js'
import { CardSkeleton } from '../components/Skeleton.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']

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
    if (runningId !== null) return
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
    <div className="space-y-10">
      <div>
        <span className="block w-10 h-px bg-[var(--color-accent)] mb-5" />
        <h1 className="font-display font-bold text-[48px] sm:text-[52px] leading-[0.98] text-[var(--color-text)]">
          데모 시나리오
        </h1>
        <p className="text-lg text-[var(--color-text)] font-medium mt-4 leading-[1.7]">
          고객을 아는 AI가 아니라, 고객의 물건을 아는 AI
        </p>
        <p className="text-sm text-[var(--color-muted)] mt-2 text-pretty">
          고정된 고객·상품·세션으로 상담을 재생해요
        </p>
      </div>

      {status === 'loading' && <CardSkeleton count={3} />}

      {status === 'error' && <ErrorBanner message={loadError} onRetry={load} />}

      {status === 'ready' && (
        <div>
          {scenarios.map((s, i) => (
            <div
              key={s.id}
              role="button"
              tabIndex={0}
              onClick={() => handleRun(s.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  handleRun(s.id)
                }
              }}
              className={`group relative overflow-hidden min-h-[220px] sm:min-h-[280px] flex items-center border-t border-[var(--color-border)] first:border-t-0 cursor-pointer focus-visible:outline focus-visible:outline-1 focus-visible:outline-[var(--color-accent)] focus-visible:-outline-offset-2 ${
                runningId !== null ? 'opacity-60 pointer-events-none' : ''
              }`}
            >
              {/* 배경 워터마크 로마숫자 — 카드 박스 대신 이걸로 순서를 표시한다 */}
              <span
                aria-hidden="true"
                className="pointer-events-none select-none absolute left-0 top-1/2 -translate-y-1/2 font-serif italic font-light text-[110px] sm:text-[190px] leading-none text-[var(--color-accent)] opacity-[0.3] transition-opacity duration-300 group-hover:opacity-[0.45]"
              >
                {ROMAN[i + 1] ?? i + 1}
              </span>

              <div className="relative z-10 max-w-[520px] space-y-3">
                <p className="font-display font-bold text-pretty text-[22px] text-[var(--color-text)]">
                  {s.title}
                </p>
                <p className="text-base text-[var(--color-muted)] leading-[1.7]">{s.narrative}</p>

                {runError?.scenarioId === s.id && (
                  <div className="pt-2" onClick={(e) => e.stopPropagation()}>
                    <ErrorBanner message={runError.message} onRetry={() => handleRun(s.id)} />
                  </div>
                )}

                <span className="block pt-1 text-sm text-[var(--color-accent)] tracking-[0.02em]">
                  {runningId === s.id ? '상담 생성 중…' : '이 시나리오 재생 →'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { HESITATION_LABELS, CTA_LABELS, CTA_CONFIRMATIONS } from '../constants.js'
import CitationCard from '../components/CitationCard.jsx'
import StatusBanner from '../components/StatusBanner.jsx'

/* 오케스트레이터 5단계의 사람 말 라벨 — 응답 trace 의 step 키와 1:1. */
const TRACE_STEP_LABELS = {
  intent: '망설임 분류',
  assets: '소유 자산 조회',
  rank: '컨디션 우선 정렬',
  clienteling: '상담 생성',
  validate: '인용 검증',
}

function SectionNumeral({ children }) {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none select-none absolute left-0 top-1/2 -translate-y-1/2 font-serif italic font-light text-[100px] sm:text-[170px] leading-none text-[var(--color-accent)] opacity-[0.3]"
    >
      {children}
    </span>
  )
}

export default function AdviseResultScreen() {
  const { state } = useLocation()
  const navigate = useNavigate()
  const advise = state?.advise
  const scenario = state?.scenario
  const [ctaConfirmed, setCtaConfirmed] = useState(false)
  const [traceOpen, setTraceOpen] = useState(false)

  if (!advise) {
    return (
      <div className="space-y-4">
        <p className="text-base text-[var(--color-muted)]">
          표시할 상담 결과가 없어요. 시나리오를 먼저 재생해주세요.
        </p>
        <Link to="/" className="text-base text-[var(--color-accent)]">
          시나리오로 돌아가기
        </Link>
      </div>
    )
  }

  const ctaLabel = CTA_LABELS[advise.cta]

  return (
    <div className="space-y-8">
      <StatusBanner degraded={advise.degraded} noAssets={advise.no_assets} />

      {scenario && (
        <div>
          <span className="text-[10px] tracking-[0.12em] text-[var(--color-muted)]">{scenario.id}</span>
          <h1 className="font-display font-bold text-pretty text-[24px] leading-snug text-[var(--color-text)] mt-1.5">
            {scenario.title}
          </h1>
        </div>
      )}

      <div>
        <div className="relative overflow-hidden min-h-[200px] sm:min-h-[240px] flex items-center border-t border-[var(--color-border)] py-14">
          <SectionNumeral>I</SectionNumeral>
          <div className="relative z-10 max-w-[520px]">
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)]">
                감지된 망설임
              </span>
              <span className="text-xs text-[var(--color-muted)]">
                신뢰도 {Math.round(advise.confidence * 100)}%
              </span>
            </div>
            <p className="font-display font-bold text-[19px] mt-2.5 text-[var(--color-text)]">
              {HESITATION_LABELS[advise.hesitation_type] ?? advise.hesitation_type}
            </p>
            {advise.signals?.length > 0 && (
              <ul className="mt-3.5 space-y-1.5">
                {advise.signals.map((sig, i) => (
                  <li key={i} className="text-sm text-[var(--color-muted)]">
                    {sig.evidence}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="relative overflow-hidden min-h-[200px] sm:min-h-[240px] flex items-center border-t border-[var(--color-border)] py-14">
          <SectionNumeral>II</SectionNumeral>
          <div className="relative z-10 max-w-[520px]">
            <p className="text-base leading-[1.85] text-[var(--color-text)]">{advise.message}</p>
            {ctaLabel && !ctaConfirmed && (
              <button
                onClick={() => setCtaConfirmed(true)}
                className="mt-5 bg-[var(--color-accent)] text-[var(--color-bg)] text-xs tracking-[0.16em] uppercase px-5 py-3 transition-opacity duration-150 hover:opacity-90"
              >
                {ctaLabel}
              </button>
            )}
            {ctaLabel && ctaConfirmed && (
              <p className="mt-5 text-sm text-[var(--color-accent)]">{CTA_CONFIRMATIONS[advise.cta]}</p>
            )}
          </div>
        </div>

        <div className="relative overflow-hidden min-h-[200px] sm:min-h-[240px] flex items-center border-t border-[var(--color-border)] py-14">
          <SectionNumeral>III</SectionNumeral>
          <div className="relative z-10 max-w-[520px]">
            <div className="flex items-baseline justify-between mb-5">
              <span className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)]">
                인용 근거
              </span>
              <span
                className={`text-[11px] tracking-[0.08em] ${
                  advise.owned_assets_used ? 'text-[var(--color-accent)]' : 'text-[var(--color-muted)]'
                }`}
              >
                {advise.owned_assets_used ? '소유 자산 근거 사용됨' : '소유 자산 근거 없음'}
              </span>
            </div>
            {advise.citations?.length > 0 ? (
              <div className="space-y-6">
                {advise.citations.map((c) => (
                  <CitationCard key={c.asset_id} citation={c} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--color-muted)]">인용된 개체가 없어요</p>
            )}
          </div>
        </div>

        {/* AI 판단 과정 — 응답 trace 그대로. 오프라인 목업에는 trace 가 없어 자동으로 숨는다. */}
        {advise.trace?.length > 0 && (
          <div className="border-t border-[var(--color-border)] pt-8">
            <button
              onClick={() => setTraceOpen((v) => !v)}
              aria-expanded={traceOpen}
              className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)] transition-colors duration-150 hover:text-[var(--color-accent)]"
            >
              AI 판단 과정 {traceOpen ? '−' : '+'}
            </button>
            {traceOpen && (
              <ol className="mt-5 space-y-3.5">
                {advise.trace.map((step, i) => (
                  <li key={step.step} className="flex items-baseline gap-3">
                    <span className="font-serif italic text-sm text-[var(--color-accent)] w-4 shrink-0">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-sm text-[var(--color-text)]">
                          {TRACE_STEP_LABELS[step.step] ?? step.step}
                        </span>
                        <span className="text-[11px] text-[var(--color-muted)] tabular-nums shrink-0">
                          {step.mode} · {step.elapsed_ms}ms
                        </span>
                      </div>
                      {step.detail && (
                        <p
                          className={`text-xs mt-0.5 ${
                            step.degraded ? 'text-[var(--color-warn)]' : 'text-[var(--color-muted)]'
                          }`}
                        >
                          {step.degraded ? '폴백 — ' : ''}
                          {step.detail}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}

        <div className="border-t border-[var(--color-border)] pt-8 flex gap-5">
          <button
            onClick={() => navigate('/')}
            className="text-sm text-[var(--color-muted)] transition-colors duration-150 hover:text-[var(--color-accent)]"
          >
            다른 시나리오
          </button>
          <Link
            to="/consult"
            className="text-sm text-[var(--color-muted)] transition-colors duration-150 hover:text-[var(--color-accent)]"
          >
            직접 상담
          </Link>
        </div>
      </div>
    </div>
  )
}

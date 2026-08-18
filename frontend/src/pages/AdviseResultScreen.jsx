import { useState } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { HESITATION_LABELS, CTA_LABELS, CTA_CONFIRMATIONS } from '../constants.js'
import CitationCard from '../components/CitationCard.jsx'
import StatusBanner from '../components/StatusBanner.jsx'

export default function AdviseResultScreen() {
  const { state } = useLocation()
  const navigate = useNavigate()
  const advise = state?.advise
  const scenario = state?.scenario
  const [ctaConfirmed, setCtaConfirmed] = useState(false)

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

      <div className="border-l-2 border-[var(--color-accent)] pl-10 flex flex-col gap-9">
        {scenario && (
          <div className="flex gap-5">
            <span className="w-[26px] shrink-0 text-[11px] tracking-[0.1em] text-[var(--color-accent)] pt-0.5">
              {scenario.id}
            </span>
            <h1 className="font-display font-bold text-pretty text-[24px] leading-snug text-[var(--color-text)]">
              {scenario.title}
            </h1>
          </div>
        )}

        <div className="flex gap-5">
          <span className="w-[26px] shrink-0 text-[11px] tracking-[0.1em] text-[var(--color-accent)] pt-0.5">
            I
          </span>
          <div className="flex-1">
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

        <div className="flex gap-5">
          <span className="w-[26px] shrink-0 text-[11px] tracking-[0.1em] text-[var(--color-accent)] pt-0.5">
            II
          </span>
          <div className="flex-1">
            <p className="text-base leading-[1.85] text-[var(--color-text)]">{advise.message}</p>
            {ctaLabel && !ctaConfirmed && (
              <button
                onClick={() => setCtaConfirmed(true)}
                className="mt-5 border border-[var(--color-accent)] text-[var(--color-accent)] text-xs tracking-[0.16em] uppercase px-5 py-3 transition-colors duration-150 hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)]"
              >
                {ctaLabel}
              </button>
            )}
            {ctaLabel && ctaConfirmed && (
              <p className="mt-5 text-sm text-[var(--color-accent)]">{CTA_CONFIRMATIONS[advise.cta]}</p>
            )}
          </div>
        </div>

        <div className="flex gap-5">
          <span className="w-[26px] shrink-0 text-[11px] tracking-[0.1em] text-[var(--color-accent)] pt-0.5">
            III
          </span>
          <div className="flex-1">
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

        <div className="flex gap-5">
          <span className="w-[26px] shrink-0" />
          <div className="flex-1 flex gap-3">
            <button
              onClick={() => navigate('/')}
              className="flex-1 text-center py-3.5 border border-[var(--color-border)] text-xs tracking-[0.14em] uppercase text-[var(--color-text)] transition-colors duration-150 hover:border-[var(--color-accent)]/40"
            >
              다른 시나리오
            </button>
            <Link
              to="/consult"
              className="flex-1 text-center py-3.5 border border-[var(--color-border)] text-xs tracking-[0.14em] uppercase text-[var(--color-text)] transition-colors duration-150 hover:border-[var(--color-accent)]/40"
            >
              직접 상담
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

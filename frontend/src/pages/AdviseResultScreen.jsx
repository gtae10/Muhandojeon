import { useLocation, useNavigate, Link } from 'react-router-dom'
import { HESITATION_LABELS, CTA_LABELS } from '../constants.js'
import CitationCard from '../components/CitationCard.jsx'
import StatusBanner from '../components/StatusBanner.jsx'

export default function AdviseResultScreen() {
  const { state } = useLocation()
  const navigate = useNavigate()
  const advise = state?.advise
  const scenario = state?.scenario

  if (!advise) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-[var(--color-muted)]">
          표시할 상담 결과가 없어요. 시나리오를 먼저 재생해주세요.
        </p>
        <Link to="/" className="text-sm text-[var(--color-accent)]">
          시나리오로 돌아가기
        </Link>
      </div>
    )
  }

  const ctaLabel = CTA_LABELS[advise.cta]

  return (
    <div className="space-y-6">
      {scenario && (
        <div>
          <span className="text-xs font-mono text-[var(--color-accent)]">{scenario.id}</span>
          <h1 className="text-base font-medium mt-1">{scenario.title}</h1>
        </div>
      )}

      <StatusBanner degraded={advise.degraded} noAssets={advise.no_assets} />

      <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--color-muted)]">감지된 망설임</span>
          <span className="text-xs text-[var(--color-muted)]">
            신뢰도 {Math.round(advise.confidence * 100)}%
          </span>
        </div>
        <p className="text-sm font-medium mt-1">
          {HESITATION_LABELS[advise.hesitation_type] ?? advise.hesitation_type}
        </p>
        {advise.signals?.length > 0 && (
          <ul className="mt-3 space-y-1 border-t border-[var(--color-border)] pt-3">
            {advise.signals.map((sig, i) => (
              <li key={i} className="text-xs text-[var(--color-muted)]">
                {sig.evidence}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-2xl bg-[var(--color-surface-raised)] p-5">
        <p className="text-sm leading-relaxed">{advise.message}</p>
        {ctaLabel && (
          <button className="w-full mt-4 py-2.5 rounded-full bg-[var(--color-accent)] text-black text-sm transition-opacity duration-150 hover:opacity-90">
            {ctaLabel}
          </button>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-[var(--color-muted)]">인용 근거</span>
          <span
            className={`text-xs ${
              advise.owned_assets_used ? 'text-[var(--color-accent)]' : 'text-[var(--color-muted)]'
            }`}
          >
            {advise.owned_assets_used ? '소유 자산 근거 사용됨' : '소유 자산 근거 없음'}
          </span>
        </div>
        {advise.citations?.length > 0 ? (
          <div className="space-y-2">
            {advise.citations.map((c) => (
              <CitationCard key={c.asset_id} citation={c} />
            ))}
          </div>
        ) : (
          <p className="text-xs text-[var(--color-muted)]">인용된 개체가 없어요</p>
        )}
      </div>

      <div className="flex gap-3 pt-2">
        <button
          onClick={() => navigate('/')}
          className="flex-1 py-2.5 rounded-full border border-[var(--color-border)] text-sm transition-colors duration-150 hover:border-[var(--color-accent)]/40"
        >
          다른 시나리오
        </button>
        <Link
          to="/consult"
          className="flex-1 text-center py-2.5 rounded-full border border-[var(--color-border)] text-sm transition-colors duration-150 hover:border-[var(--color-accent)]/40"
        >
          직접 상담
        </Link>
      </div>
    </div>
  )
}

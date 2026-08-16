export default function CitationCard({ citation }) {
  return (
    <div className="rounded-xl border border-[var(--color-accent)]/30 bg-[var(--color-accent-soft)] px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{citation.product_name}</p>
        <span className="text-xs text-[var(--color-accent)]">
          컨디션 {citation.condition_score}점
        </span>
      </div>
      {citation.headline_finding && (
        <p className="text-xs text-[var(--color-muted)] mt-1">{citation.headline_finding}</p>
      )}
      {citation.next_service_months <= 3 && (
        <p className="text-xs text-[var(--color-warn)] mt-1">
          {citation.next_service_months === 0
            ? '즉시 케어 권장'
            : `${citation.next_service_months}개월 내 케어 권장`}
        </p>
      )}
    </div>
  )
}

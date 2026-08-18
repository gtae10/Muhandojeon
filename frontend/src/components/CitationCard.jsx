export default function CitationCard({ citation }) {
  return (
    <div className="flex items-start justify-between gap-6">
      <div>
        <p className="font-display text-base text-[var(--color-text)]">{citation.product_name}</p>
        {citation.headline_finding && (
          <p className="text-xs text-[var(--color-muted)] mt-1.5">{citation.headline_finding}</p>
        )}
        {citation.next_service_months <= 3 && (
          <p className="text-[11px] text-[var(--color-warn)] mt-1.5">
            {citation.next_service_months === 0
              ? '즉시 케어 권장'
              : `${citation.next_service_months}개월 내 케어 권장`}
          </p>
        )}
      </div>
      <p className="font-display italic text-base text-[var(--color-accent)] whitespace-nowrap">
        {citation.condition_score}점
      </p>
    </div>
  )
}

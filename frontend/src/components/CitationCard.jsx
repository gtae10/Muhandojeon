// asset_id를 시드로 결(grain) 패턴을 만든다 — 개체마다 다른 무늬가 나오게 하기 위한
// 순수 해시일 뿐, 암호학적 용도가 아니다.
function hashSeed(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return h
}

/** 컨디션 점수를 진행 아치로, asset_id 고유의 결 무늬를 안쪽에 새긴 검사 링. */
function InspectionRing({ score, seedKey, warn }) {
  const seed = hashSeed(seedKey)
  const r = 18
  const c = 2 * Math.PI * r
  const progress = (Math.max(0, Math.min(100, score)) / 100) * c
  const ringColor = warn ? 'var(--color-warn)' : 'var(--color-accent)'
  const grains = [6, 9, 12.5].map((gr, i) => ({
    r: gr,
    rotate: (seed * (i * 6 + 7)) % 360,
    dash: `${gr * (2.1 + (i % 2) * 0.6)} ${2 * Math.PI * gr}`,
  }))

  return (
    <div className="relative w-12 h-12 shrink-0">
      <svg viewBox="0 0 44 44" className="w-12 h-12">
        <circle cx="22" cy="22" r={r} fill="none" stroke="var(--color-border)" strokeWidth="1.5" />
        {grains.map((g, i) => (
          <circle
            key={i}
            cx="22"
            cy="22"
            r={g.r}
            fill="none"
            stroke="var(--color-text)"
            strokeWidth="0.75"
            opacity="0.16"
            strokeDasharray={g.dash}
            transform={`rotate(${g.rotate} 22 22)`}
          />
        ))}
        <circle
          cx="22"
          cy="22"
          r={r}
          fill="none"
          stroke={ringColor}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeDasharray={`${progress} ${c}`}
          transform="rotate(-90 22 22)"
        />
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center font-display font-bold tabular-nums text-sm"
        style={{ color: ringColor }}
      >
        {score}
      </span>
    </div>
  )
}

export default function CitationCard({ citation }) {
  const warn = citation.next_service_months <= 3

  return (
    <div className="flex items-start justify-between gap-5">
      <div className="min-w-0">
        <p className="font-display font-semibold text-lg text-[var(--color-text)]">
          {citation.product_name}
        </p>
        {citation.headline_finding && (
          <p className="text-sm text-[var(--color-muted)] mt-1.5">{citation.headline_finding}</p>
        )}
        {warn && (
          <p className="text-xs text-[var(--color-warn)] mt-1.5">
            {citation.next_service_months === 0
              ? '즉시 케어 권장'
              : `${citation.next_service_months}개월 내 케어 권장`}
          </p>
        )}
      </div>
      <div className="flex flex-col items-center gap-1 shrink-0">
        <InspectionRing score={citation.condition_score} seedKey={citation.asset_id} warn={warn} />
        <span className="text-[10px] tracking-[0.1em] text-[var(--color-muted)]">점수</span>
      </div>
    </div>
  )
}

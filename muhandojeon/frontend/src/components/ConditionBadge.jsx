// TODO(기획·디자인): 점수 구간별 색상/문구 브랜드 톤에 맞춰 조정
export default function ConditionBadge({ score }) {
  const label = score >= 85 ? '양호' : score >= 60 ? '주의' : '점검 필요'

  return (
    <div className="rounded-2xl border border-white/10 p-5 flex items-center justify-between">
      <div>
        <p className="text-xs text-[var(--color-muted)]">컨디션 점수</p>
        <p className="text-3xl font-semibold mt-1">{score}</p>
      </div>
      <span className="text-xs px-3 py-1 rounded-full border border-[var(--color-accent)] text-[var(--color-accent)]">
        {label}
      </span>
    </div>
  )
}

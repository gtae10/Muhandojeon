export default function StatusBanner({ degraded, noAssets }) {
  if (!degraded && !noAssets) return null

  return (
    <div className="space-y-2">
      {degraded && (
        <div className="border border-[var(--color-warn)]/40 px-3.5 py-2.5 text-sm text-[var(--color-warn)]">
          일부 모듈이 응답하지 않아 폴백으로 처리됐어요 (데모는 계속 진행돼요)
        </div>
      )}
      {noAssets && (
        <div className="border border-[var(--color-border)] px-3.5 py-2.5 text-sm text-[var(--color-muted)]">
          이 고객은 아직 등록된 소유 개체가 없어요 — 일반 제안 모드로 상담해요
        </div>
      )}
    </div>
  )
}

export function CardSkeleton({ count = 3 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 animate-pulse"
        >
          <div className="h-3 w-16 rounded bg-[var(--color-surface-raised)]" />
          <div className="h-4 w-3/4 rounded bg-[var(--color-surface-raised)] mt-3" />
          <div className="h-3 w-full rounded bg-[var(--color-surface-raised)] mt-3" />
          <div className="h-3 w-2/3 rounded bg-[var(--color-surface-raised)] mt-2" />
          <div className="h-9 w-full rounded-full bg-[var(--color-surface-raised)] mt-4" />
        </div>
      ))}
    </div>
  )
}

export function FieldSkeleton({ count = 2 }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="animate-pulse">
          <div className="h-3 w-16 rounded bg-[var(--color-surface-raised)] mb-2" />
          <div className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]" />
        </div>
      ))}
    </div>
  )
}

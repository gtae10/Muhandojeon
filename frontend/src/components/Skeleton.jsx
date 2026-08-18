export function CardSkeleton({ count = 3 }) {
  return (
    <div className="divide-y divide-[var(--color-border)]">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="py-7 first:pt-0 last:pb-0 animate-pulse">
          <div className="h-2.5 w-10 bg-[var(--color-surface)]" />
          <div className="h-4 w-3/4 bg-[var(--color-surface)] mt-3" />
          <div className="h-3 w-full bg-[var(--color-surface)] mt-3.5" />
          <div className="h-3 w-2/3 bg-[var(--color-surface)] mt-2" />
          <div className="h-10 w-full bg-[var(--color-surface)] mt-5" />
        </div>
      ))}
    </div>
  )
}

export function FieldSkeleton({ count = 2 }) {
  return (
    <div className="space-y-6">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="animate-pulse">
          <div className="h-2.5 w-14 bg-[var(--color-surface)] mb-2.5" />
          <div className="h-10 w-full border border-[var(--color-border)] bg-[var(--color-surface)]" />
        </div>
      ))}
    </div>
  )
}

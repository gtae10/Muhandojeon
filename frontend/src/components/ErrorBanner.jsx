export default function ErrorBanner({ message, onRetry }) {
  return (
    <div className="border border-[var(--color-danger)]/40 px-3.5 py-3 flex items-center justify-between gap-3">
      <p className="text-xs text-[var(--color-danger)] leading-relaxed">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 border border-[var(--color-danger)]/40 px-3 py-1.5 text-xs text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10"
        >
          다시 시도
        </button>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCustomers, getCatalog, advise, ApiError } from '../api/client.js'
import { FieldSkeleton } from '../components/Skeleton.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ConsultScreen() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState([])
  const [products, setProducts] = useState([])
  const [customerId, setCustomerId] = useState('')
  const [productId, setProductId] = useState('')
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [loadError, setLoadError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  function load() {
    setStatus('loading')
    setLoadError(null)
    Promise.all([getCustomers(), getCatalog()])
      .then(([customersRes, catalogRes]) => {
        setCustomers(customersRes.items ?? [])
        setProducts(catalogRes.items ?? [])
        setStatus('ready')
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : '목록을 불러오지 못했어요')
        setStatus('error')
      })
  }

  useEffect(() => {
    load()
  }, [])

  async function handleSubmit() {
    if (!customerId || !productId) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const result = await advise({ customer_id: customerId, target_product_id: productId })
      navigate('/result', { state: { advise: result } })
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : '상담 생성에 실패했어요')
    } finally {
      setSubmitting(false)
    }
  }

  const header = (
    <div>
      <h1 className="font-display font-bold text-2xl text-[var(--color-text)]">직접 상담</h1>
      <p className="text-sm text-[var(--color-muted)] mt-2 text-pretty">
        세션 이벤트 없이 호출해요 — 일반 제안 모드로 상담이 생성돼요
      </p>
    </div>
  )

  if (status === 'loading') {
    return (
      <div className="space-y-8">
        {header}
        <FieldSkeleton count={2} />
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="space-y-8">
        {header}
        <ErrorBanner message={loadError} onRetry={load} />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {header}

      <div className="space-y-6">
        <div>
          <label className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)] block mb-2.5">
            고객
          </label>
          <select
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] px-3 py-2.5 text-base text-[var(--color-text)]"
          >
            <option value="">선택하세요</option>
            {customers.map((c) => (
              <option key={c.customer_id} value={c.customer_id}>
                {c.display_name} · {c.tier} · 보유 {c.asset_count}개
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)] block mb-2.5">
            상담 대상 상품
          </label>
          <select
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] px-3 py-2.5 text-base text-[var(--color-text)]"
          >
            <option value="">선택하세요</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.name} · {p.collection}
              </option>
            ))}
          </select>
        </div>

        {submitError && <ErrorBanner message={submitError} onRetry={handleSubmit} />}

        <button
          onClick={handleSubmit}
          disabled={!customerId || !productId || submitting}
          className="w-full py-3 border border-[var(--color-accent)] text-[var(--color-accent)] text-xs tracking-[0.14em] uppercase transition-colors duration-150 hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-[var(--color-accent)]"
        >
          {submitting ? '상담 생성 중…' : '상담 생성'}
        </button>
        {(!customerId || !productId) && (
          <p className="text-sm text-[var(--color-muted)] text-center">
            고객과 상품을 모두 선택하면 상담을 생성할 수 있어요
          </p>
        )}
      </div>
    </div>
  )
}

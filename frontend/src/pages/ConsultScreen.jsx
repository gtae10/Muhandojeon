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
      <h1 className="text-lg font-medium">직접 상담</h1>
      <p className="text-xs text-[var(--color-muted)] mt-1">
        세션 이벤트 없이 호출해요 — 일반 제안 모드로 상담이 생성돼요
      </p>
    </div>
  )

  if (status === 'loading') {
    return (
      <div className="space-y-6">
        {header}
        <FieldSkeleton count={2} />
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="space-y-6">
        {header}
        <ErrorBanner message={loadError} onRetry={load} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {header}

      <div className="space-y-4">
        <div>
          <label className="text-xs text-[var(--color-muted)] block mb-2">고객</label>
          <select
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
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
          <label className="text-xs text-[var(--color-muted)] block mb-2">상담 대상 상품</label>
          <select
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
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
          className="w-full py-2.5 rounded-full bg-[var(--color-accent)] text-black text-sm transition-opacity duration-150 hover:opacity-90 disabled:opacity-50 disabled:hover:opacity-50"
        >
          {submitting ? '상담 생성 중…' : '상담 생성'}
        </button>
      </div>
    </div>
  )
}

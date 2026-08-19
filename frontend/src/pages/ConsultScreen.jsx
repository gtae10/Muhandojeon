import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCustomers, getCatalog, advise, ApiError } from '../api/client.js'
import { FieldSkeleton } from '../components/Skeleton.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Select from '../components/Select.jsx'

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
      <span className="block w-10 h-px bg-[var(--color-accent)] mb-5" />
      <h1 className="font-display font-bold text-[48px] sm:text-[52px] leading-[0.98] text-[var(--color-text)]">
        직접 상담
      </h1>
      <p className="text-base text-[var(--color-muted)] mt-4 leading-[1.7] text-pretty max-w-[46ch]">
        세션 이벤트 없이 호출해요 — 일반 제안 모드로 상담이 생성돼요
      </p>
    </div>
  )

  if (status === 'loading') {
    return (
      <div className="space-y-10">
        {header}
        <FieldSkeleton count={2} />
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="space-y-10">
        {header}
        <ErrorBanner message={loadError} onRetry={load} />
      </div>
    )
  }

  const customerOptions = customers.map((c) => ({
    value: c.customer_id,
    label: `${c.display_name} · ${c.tier} · 보유 ${c.asset_count}개`,
  }))
  const productOptions = products.map((p) => ({
    value: p.product_id,
    label: `${p.name} · ${p.collection}`,
  }))

  return (
    <div className="space-y-10">
      {header}

      <div className="space-y-8">
        <div>
          <label className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)] block mb-3">
            고객
          </label>
          <Select value={customerId} onChange={setCustomerId} options={customerOptions} />
        </div>

        <div>
          <label className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)] block mb-3">
            상담 대상 상품
          </label>
          <Select value={productId} onChange={setProductId} options={productOptions} />
        </div>

        {submitError && <ErrorBanner message={submitError} onRetry={handleSubmit} />}

        <button
          onClick={handleSubmit}
          disabled={!customerId || !productId || submitting}
          className="w-full py-4 bg-[var(--color-accent)] text-[var(--color-bg)] text-xs tracking-[0.14em] uppercase transition-opacity duration-150 hover:opacity-90 disabled:opacity-40"
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

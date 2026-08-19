import { useEffect, useRef, useState } from 'react'
import {
  getCustomers,
  getCatalog,
  getCustomerAssets,
  classifyIntent,
  clientelingReply,
  ApiError,
} from '../api/client.js'
import { HESITATION_LABELS, CTA_LABELS, CTA_CONFIRMATIONS } from '../constants.js'
import { FieldSkeleton } from '../components/Skeleton.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import CitationCard from '../components/CitationCard.jsx'

const SEVERITY_RANK = { HIGH: 2, MEDIUM: 1, LOW: 0 }

function headlineFinding(asset) {
  if (!asset.findings?.length) return null
  return [...asset.findings].sort(
    (a, b) => (SEVERITY_RANK[b.severity] ?? -1) - (SEVERITY_RANK[a.severity] ?? -1),
  )[0].note
}

/** ClientelingReplyResponse 는 cited_asset_ids(문자열)만 준다 — 카드 렌더에 필요한
 * product_name/condition_score 등은 세션 시작 때 미리 조회해 둔 owned_assets 에서 찾는다. */
function buildCitations(citedAssetIds, ownedAssets) {
  if (!citedAssetIds?.length) return []
  return citedAssetIds
    .map((id) => ownedAssets.find((a) => a.asset_id === id))
    .filter(Boolean)
    .map((a) => ({
      asset_id: a.asset_id,
      product_name: a.product_name,
      condition_score: a.condition_score,
      next_service_months: a.next_service_months,
      headline_finding: headlineFinding(a),
    }))
}

export default function FreeChatScreen() {
  // 설정 단계
  const [stage, setStage] = useState('setup') // setup | classifying | chat
  const [customers, setCustomers] = useState([])
  const [products, setProducts] = useState([])
  const [loadStatus, setLoadStatus] = useState('loading') // loading | ready | error
  const [loadError, setLoadError] = useState(null)
  const [customerId, setCustomerId] = useState('')
  const [productId, setProductId] = useState('')
  const [classifyError, setClassifyError] = useState(null)

  // 채팅 단계 — 세션 시작 시 한 번만 채워진다
  const [targetProduct, setTargetProduct] = useState(null)
  const [ownedAssets, setOwnedAssets] = useState([])
  const [hesitation, setHesitation] = useState(null) // IntentClassifyResponse

  // 대화
  const [messages, setMessages] = useState([]) // { role, content, citedAssetIds?, cta? }
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState(null) // { message, retryHistory }
  const [ctaConfirmed, setCtaConfirmed] = useState(() => new Set())
  const scrollRef = useRef(null)

  function loadOptions() {
    setLoadStatus('loading')
    setLoadError(null)
    Promise.all([getCustomers(), getCatalog()])
      .then(([customersRes, catalogRes]) => {
        setCustomers(customersRes.items ?? [])
        setProducts(catalogRes.items ?? [])
        setLoadStatus('ready')
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : '목록을 불러오지 못했어요')
        setLoadStatus('error')
      })
  }

  useEffect(() => {
    loadOptions()
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  async function startSession() {
    if (!customerId || !productId) return
    const product = products.find((p) => p.product_id === productId)
    if (!product) return

    setStage('classifying')
    setClassifyError(null)
    try {
      // AI1 이 실제로 붙기 전까지는 진짜 브라우징 이벤트가 없다. 지금 이 상품을
      // 보고 있다는 최소 합성 이벤트 하나로 /intent/classify 를 채운다.
      const [assetsRes, intentRes] = await Promise.all([
        getCustomerAssets(customerId),
        classifyIntent({
          customer_id: customerId,
          session_events: [
            {
              event_type: 'view_product',
              product_id: product.product_id,
              timestamp: new Date().toISOString(),
            },
          ],
        }),
      ])
      setTargetProduct(product)
      setOwnedAssets(assetsRes.assets ?? [])
      setHesitation(intentRes)
      setMessages([])
      setSendError(null)
      setCtaConfirmed(new Set())
      setStage('chat')
    } catch (err) {
      setClassifyError(err instanceof ApiError ? err.message : '세션을 시작하지 못했어요')
      setStage('setup')
    }
  }

  function resetSession() {
    setStage('setup')
    setTargetProduct(null)
    setOwnedAssets([])
    setHesitation(null)
    setMessages([])
    setSendError(null)
  }

  async function sendToAdvisor(historyWithNewMessage) {
    setSending(true)
    setSendError(null)
    try {
      const res = await clientelingReply({
        customer_id: customerId,
        hesitation_type: hesitation.hesitation_type,
        target_product: targetProduct,
        owned_assets: ownedAssets,
        strategy_id: 'S2',
        history: historyWithNewMessage.map(({ role, content }) => ({ role, content })),
      })
      setMessages((prev) => [
        ...prev,
        { role: 'advisor', content: res.message, citedAssetIds: res.cited_asset_ids, cta: res.cta },
      ])
    } catch (err) {
      setSendError({
        message: err instanceof ApiError ? err.message : '상담 응답을 받지 못했어요',
        retryHistory: historyWithNewMessage,
      })
    } finally {
      setSending(false)
    }
  }

  function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    const nextHistory = [...messages, { role: 'customer', content: text }]
    setMessages(nextHistory)
    setInput('')
    sendToAdvisor(nextHistory)
  }

  function confirmCta(index) {
    setCtaConfirmed((prev) => new Set(prev).add(index))
  }

  const header = (
    <div>
      <h1 className="font-display font-bold text-2xl text-[var(--color-text)]">자유 상담</h1>
      <p className="text-sm text-[var(--color-muted)] mt-2 text-pretty">
        고객·상품을 고르면 망설임 유형을 자동으로 감지한 뒤, 자유롭게 대화할 수 있어요
      </p>
    </div>
  )

  // ---- 설정 단계 ----
  if (stage === 'setup' || stage === 'classifying') {
    if (loadStatus === 'loading') {
      return (
        <div className="space-y-8">
          {header}
          <FieldSkeleton count={2} />
        </div>
      )
    }
    if (loadStatus === 'error') {
      return (
        <div className="space-y-8">
          {header}
          <ErrorBanner message={loadError} onRetry={loadOptions} />
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
              disabled={stage === 'classifying'}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] px-3 py-2.5 text-base text-[var(--color-text)] disabled:opacity-50"
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
              disabled={stage === 'classifying'}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] px-3 py-2.5 text-base text-[var(--color-text)] disabled:opacity-50"
            >
              <option value="">선택하세요</option>
              {products.map((p) => (
                <option key={p.product_id} value={p.product_id}>
                  {p.name} · {p.collection}
                </option>
              ))}
            </select>
          </div>

          {classifyError && <ErrorBanner message={classifyError} onRetry={startSession} />}

          {stage === 'classifying' ? (
            <div className="border border-[var(--color-border)] px-3.5 py-3 flex items-center gap-2.5 animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] shrink-0" />
              <span className="text-sm text-[var(--color-muted)]">망설임 유형 감지 중…</span>
            </div>
          ) : (
            <button
              onClick={startSession}
              disabled={!customerId || !productId}
              className="w-full py-3 border border-[var(--color-accent)] text-[var(--color-accent)] text-xs tracking-[0.14em] uppercase transition-colors duration-150 hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-[var(--color-accent)]"
            >
              상담 시작
            </button>
          )}
          {stage === 'setup' && (!customerId || !productId) && (
            <p className="text-sm text-[var(--color-muted)] text-center">
              고객과 상품을 모두 선택하면 상담을 시작할 수 있어요
            </p>
          )}
        </div>
      </div>
    )
  }

  // ---- 채팅 단계 ----
  return (
    <div className="flex flex-col h-[calc(100vh-160px)]">
      <div className="pb-5 border-b border-[var(--color-border)] flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-[var(--color-muted)] truncate">
            {customers.find((c) => c.customer_id === customerId)?.display_name} · {targetProduct.name}
          </p>
          <div className="flex items-baseline gap-2 mt-1.5">
            <span className="font-display font-semibold text-base text-[var(--color-text)]">
              {HESITATION_LABELS[hesitation.hesitation_type] ?? hesitation.hesitation_type}
            </span>
            <span className="text-xs text-[var(--color-muted)]">
              신뢰도 {Math.round(hesitation.confidence * 100)}%
            </span>
          </div>
        </div>
        <button
          onClick={resetSession}
          className="shrink-0 text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] whitespace-nowrap"
        >
          새 상담 시작
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto py-6 space-y-6">
        {messages.length === 0 && (
          <p className="text-sm text-[var(--color-muted)] text-center py-8">
            메시지를 보내 상담을 시작해보세요
          </p>
        )}
        {messages.map((m, i) => {
          const isCustomer = m.role === 'customer'
          const citations = isCustomer ? [] : buildCitations(m.citedAssetIds, ownedAssets)
          const ctaLabel = !isCustomer ? CTA_LABELS[m.cta] : null
          return (
            <div key={i} className={`flex ${isCustomer ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] ${isCustomer ? 'items-end' : 'items-start'} flex flex-col gap-3`}>
                <div
                  className={
                    isCustomer
                      ? 'bg-[var(--color-accent)] text-[var(--color-bg)] px-4 py-2.5 text-sm leading-relaxed'
                      : 'border border-[var(--color-border)] px-4 py-2.5 text-sm leading-relaxed text-[var(--color-text)]'
                  }
                >
                  {m.content}
                </div>
                {citations.length > 0 && (
                  <div className="w-full space-y-4 pl-1">
                    {citations.map((c) => (
                      <CitationCard key={c.asset_id} citation={c} />
                    ))}
                  </div>
                )}
                {ctaLabel && !ctaConfirmed.has(i) && (
                  <button
                    onClick={() => confirmCta(i)}
                    className="border border-[var(--color-accent)] text-[var(--color-accent)] text-xs tracking-[0.14em] uppercase px-4 py-2.5 transition-colors duration-150 hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)]"
                  >
                    {ctaLabel}
                  </button>
                )}
                {ctaLabel && ctaConfirmed.has(i) && (
                  <p className="text-sm text-[var(--color-accent)]">{CTA_CONFIRMATIONS[m.cta]}</p>
                )}
              </div>
            </div>
          )
        })}
        {sending && (
          <div className="flex justify-start">
            <div className="border border-[var(--color-border)] px-4 py-2.5 text-sm text-[var(--color-muted)] animate-pulse">
              상담 작성 중…
            </div>
          </div>
        )}
      </div>

      {sendError && (
        <div className="pb-3">
          <ErrorBanner message={sendError.message} onRetry={() => sendToAdvisor(sendError.retryHistory)} />
        </div>
      )}

      <div className="pt-4 border-t border-[var(--color-border)] flex gap-2.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          disabled={sending}
          placeholder="메시지를 입력하세요"
          className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] px-3 py-2.5 text-base text-[var(--color-text)] disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="shrink-0 px-5 py-2.5 border border-[var(--color-accent)] text-[var(--color-accent)] text-xs tracking-[0.14em] uppercase transition-colors duration-150 hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-[var(--color-accent)]"
        >
          전송
        </button>
      </div>
    </div>
  )
}

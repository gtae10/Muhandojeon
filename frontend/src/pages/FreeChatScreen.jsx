import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
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
import Select from '../components/Select.jsx'

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

/** 빈 대화 상태를 그냥 비워두지 않고 카드 안의 라인아트 아이콘으로 채운다. */
function EmptyChatIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 40 40"
      fill="none"
      stroke="var(--color-accent)"
      strokeWidth="1.1"
      className="opacity-80"
    >
      <path
        d="M8 11h24a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H17l-7 6v-6H8a2 2 0 0 1-2-2V13a2 2 0 0 1 2-2Z"
        strokeLinejoin="round"
      />
      <circle cx="14.5" cy="19.5" r="1.1" fill="var(--color-accent)" stroke="none" />
      <circle cx="20" cy="19.5" r="1.1" fill="var(--color-accent)" stroke="none" />
      <circle cx="25.5" cy="19.5" r="1.1" fill="var(--color-accent)" stroke="none" />
    </svg>
  )
}

export default function FreeChatScreen() {
  // 설정 단계
  const [stage, setStage] = useState('setup') // setup | classifying | chat
  const [customers, setCustomers] = useState([])
  const [products, setProducts] = useState([])
  const [loadStatus, setLoadStatus] = useState('loading') // loading | ready | error
  const [loadError, setLoadError] = useState(null)
  // 개체 식별(/identify)에서 "이 고객으로 상담 시작"으로 넘어오면 고객이 미리 채워진다
  const [searchParams] = useSearchParams()
  const [customerId, setCustomerId] = useState(() => searchParams.get('customer') ?? '')
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
      <span className="block w-10 h-px bg-[var(--color-accent)] mb-5" />
      <h1 className="font-display font-bold text-[48px] sm:text-[52px] leading-[0.98] text-[var(--color-text)]">
        자유 상담
      </h1>
      <p className="text-lg text-[var(--color-muted)] mt-4 leading-[1.7] text-pretty max-w-[50ch]">
        고객·상품을 고르면 망설임 유형을 자동으로 감지한 뒤, 자유롭게 대화할 수 있어요
      </p>
    </div>
  )

  // ---- 설정 단계 ----
  if (stage === 'setup' || stage === 'classifying') {
    if (loadStatus === 'loading') {
      return (
        <div className="space-y-10">
          {header}
          <FieldSkeleton count={2} />
        </div>
      )
    }
    if (loadStatus === 'error') {
      return (
        <div className="space-y-10">
          {header}
          <ErrorBanner message={loadError} onRetry={loadOptions} />
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

        <div className="border border-[var(--color-border)] bg-[var(--color-surface)] p-8 sm:p-10 space-y-8">
          <div>
            <label className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)] block mb-3">
              고객
            </label>
            <Select
              value={customerId}
              onChange={setCustomerId}
              options={customerOptions}
              disabled={stage === 'classifying'}
            />
          </div>

          <div>
            <label className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)] block mb-3">
              상담 대상 상품
            </label>
            <Select
              value={productId}
              onChange={setProductId}
              options={productOptions}
              disabled={stage === 'classifying'}
            />
          </div>

          {classifyError && <ErrorBanner message={classifyError} onRetry={startSession} />}

          {stage === 'classifying' ? (
            <div className="border border-[var(--color-border)] px-4 py-3.5 flex items-center gap-2.5 animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] shrink-0" />
              <span className="text-sm text-[var(--color-muted)]">망설임 유형 감지 중…</span>
            </div>
          ) : (
            <button
              onClick={startSession}
              disabled={!customerId || !productId}
              className="w-full py-4 bg-[var(--color-accent)] text-[var(--color-bg)] text-xs tracking-[0.14em] uppercase transition-opacity duration-150 hover:opacity-90 disabled:opacity-40"
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
  const customerName = customers.find((c) => c.customer_id === customerId)?.display_name ?? ''

  return (
    <div className="flex flex-col h-[calc(100vh-160px)]">
      <div className="flex justify-end mb-3">
        <button
          onClick={resetSession}
          className="shrink-0 text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] whitespace-nowrap"
        >
          새 상담 시작
        </button>
      </div>

      <div className="border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <div className="w-11 h-11 shrink-0 rounded-full border border-[var(--color-accent)]/40 bg-[var(--color-surface-raised)] flex items-center justify-center font-serif text-lg text-[var(--color-accent)]">
            {customerName.charAt(0) || '?'}
          </div>
          <div className="min-w-0">
            <p className="text-sm text-[var(--color-text)] font-medium truncate">{customerName}</p>
            <p className="font-serif italic text-base text-[var(--color-muted)] truncate">
              {targetProduct.name}
            </p>
          </div>
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1.5">
          <span className="inline-flex items-center border border-[var(--color-accent)]/40 text-[var(--color-accent)] text-[11px] tracking-[0.1em] uppercase px-2.5 py-1 whitespace-nowrap">
            {HESITATION_LABELS[hesitation.hesitation_type] ?? hesitation.hesitation_type}
          </span>
          <span className="text-[11px] text-[var(--color-muted)] whitespace-nowrap">
            신뢰도 {Math.round(hesitation.confidence * 100)}%
          </span>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto py-8">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="flex flex-col items-center gap-4 text-center px-10 py-12 border border-[var(--color-border)] max-w-md mx-auto">
              <EmptyChatIcon />
              <p className="text-sm text-[var(--color-muted)] leading-[1.7]">
                메시지를 남겨주시면
                <br />
                상담을 시작합니다
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-7">
            {messages.map((m, i) => {
              const isCustomer = m.role === 'customer'
              const citations = isCustomer ? [] : buildCitations(m.citedAssetIds, ownedAssets)
              const ctaLabel = !isCustomer ? CTA_LABELS[m.cta] : null
              return (
                <div key={i} className={`flex ${isCustomer ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[92%] sm:max-w-[80%] ${isCustomer ? 'items-end' : 'items-start'} flex flex-col gap-3`}
                  >
                    <div
                      className={
                        isCustomer
                          ? 'bg-[var(--color-surface)] border border-[var(--color-accent)]/40 px-5 py-4 text-base leading-[1.7] text-[var(--color-text)]'
                          : 'border border-[var(--color-border)] border-l-[var(--color-accent)]/70 px-5 py-4 text-base leading-[1.7] text-[var(--color-text)]'
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
                        className="bg-[var(--color-accent)] text-[var(--color-bg)] text-xs tracking-[0.14em] uppercase px-4 py-2.5 transition-opacity duration-150 hover:opacity-90"
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
                <div className="border border-[var(--color-border)] px-5 py-4 text-base text-[var(--color-muted)] animate-pulse">
                  상담 작성 중…
                </div>
              </div>
            )}
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
          className="flex-1 min-w-0 bg-[var(--color-surface)] border border-[var(--color-border)] px-3 py-2.5 text-base text-[var(--color-text)] disabled:opacity-50"
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

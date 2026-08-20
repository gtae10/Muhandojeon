import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getFingerprintSamples, fingerprintMatch, ApiError } from '../api/client.js'
import CitationCard from '../components/CitationCard.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

/* 결 무늬 라벨 — 등록 이미지 파일명(handle_01 등)을 사람 말로. */
const PART_LABELS = {
  handle: '핸들',
  corner: '코너',
  stitching: '스티치',
  hardware: '하드웨어',
}

function partLabel(label) {
  const part = label.replace(/_\d+$/, '')
  return PART_LABELS[part] ?? part
}

function SectionNumeral({ children }) {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none select-none absolute left-0 top-1/2 -translate-y-1/2 font-serif italic font-light text-[100px] sm:text-[170px] leading-none text-[var(--color-accent)] opacity-[0.3]"
    >
      {children}
    </span>
  )
}

/** 업로드 사진을 판독용 크기로 줄인다 — 원본 그대로 올리면 본문이 수 MB 로 커진다. */
async function downscaleToBase64(file, maxSide = 1280) {
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('사진을 읽지 못했어요'))
    reader.readAsDataURL(file)
  })
  const img = await new Promise((resolve, reject) => {
    const el = new Image()
    el.onload = () => resolve(el)
    el.onerror = () => reject(new Error('사진 형식을 해석하지 못했어요'))
    el.src = dataUrl
  })
  const scale = Math.min(1, maxSide / Math.max(img.width, img.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(img.width * scale)
  canvas.height = Math.round(img.height * scale)
  canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
  const scaled = canvas.toDataURL('image/jpeg', 0.8)
  return { previewUrl: scaled, base64: scaled.split(',')[1] }
}

/* 판독 연출 최소 시간 — 결과가 너무 빨리 튀어나오면 대조 과정이 안 보인다.
   모션 축소 설정이면 연출 없이 바로 결과를 보여준다. */
const SCAN_MS = 1300

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** 썸네일 한 장 — 이미지가 로드되지 않는 환경(오프라인 목업)에서는 라벨 타일로 대체. */
function QueryThumb({ image, selected, onSelect }) {
  const [broken, setBroken] = useState(false)
  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      className={`relative aspect-square overflow-hidden border transition-colors duration-150 ${
        selected
          ? 'border-[var(--color-accent)]'
          : 'border-[var(--color-border)] hover:border-[var(--color-accent)]/50'
      }`}
    >
      {broken ? (
        <span className="absolute inset-0 flex items-center justify-center bg-[var(--color-surface)] text-[11px] text-[var(--color-muted)]">
          {partLabel(image.label)}
        </span>
      ) : (
        <img
          src={image.url}
          alt={`등록 결 무늬 — ${partLabel(image.label)}`}
          loading="lazy"
          onError={() => setBroken(true)}
          className="absolute inset-0 w-full h-full object-cover"
        />
      )}
      <span className="absolute left-0 bottom-0 right-0 px-1.5 py-1 text-[10px] tracking-[0.08em] text-[var(--color-text)] bg-[var(--color-bg)]/70">
        {partLabel(image.label)}
      </span>
    </button>
  )
}

export default function FingerprintScreen() {
  const navigate = useNavigate()
  const [samples, setSamples] = useState([])
  const [loadStatus, setLoadStatus] = useState('loading') // loading | ready | error
  const [loadError, setLoadError] = useState(null)

  // 질의 이미지 — 등록 샘플({kind:'sample'}) 또는 업로드({kind:'upload'})
  const [query, setQuery] = useState(null)
  const [scanning, setScanning] = useState(false)
  const [result, setResult] = useState(null) // FingerprintMatchResponse
  const [matchError, setMatchError] = useState(null)
  const fileRef = useRef(null)

  function load() {
    setLoadStatus('loading')
    setLoadError(null)
    getFingerprintSamples()
      .then((data) => {
        setSamples(data.items ?? [])
        setLoadStatus('ready')
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : '등록 개체를 불러오지 못했어요')
        setLoadStatus('error')
      })
  }

  useEffect(() => {
    load()
  }, [])

  function selectSample(sample, image) {
    setQuery({ kind: 'sample', assetId: sample.asset_id, image })
    setResult(null)
    setMatchError(null)
  }

  async function selectUpload(file) {
    if (!file) return
    try {
      const { previewUrl, base64 } = await downscaleToBase64(file)
      setQuery({ kind: 'upload', name: file.name, previewUrl, base64 })
      setResult(null)
      setMatchError(null)
    } catch (err) {
      setMatchError(err.message)
    }
  }

  async function identify() {
    if (!query || scanning) return
    setScanning(true)
    setResult(null)
    setMatchError(null)
    const payload =
      query.kind === 'sample'
        ? { image_path: query.image.path, top_k: 3 }
        : { image_base64: query.base64, top_k: 3 }
    const minDelay = prefersReducedMotion()
      ? Promise.resolve()
      : new Promise((resolve) => setTimeout(resolve, SCAN_MS))
    try {
      const [res] = await Promise.all([fingerprintMatch(payload), minDelay])
      setResult(res)
    } catch (err) {
      setMatchError(err instanceof ApiError ? err.message : '판독에 실패했어요')
    } finally {
      setScanning(false)
    }
  }

  const matchedSample = result?.matched_asset_id
    ? samples.find((s) => s.asset_id === result.matched_asset_id)
    : null
  const previewUrl = query?.kind === 'sample' ? query.image.url : query?.previewUrl

  return (
    <div className="space-y-10">
      <div>
        <span className="block w-10 h-px bg-[var(--color-accent)] mb-5" />
        <h1 className="font-display font-bold text-[48px] sm:text-[52px] leading-[0.98] text-[var(--color-text)]">
          개체 식별
        </h1>
        <p className="text-lg text-[var(--color-text)] font-medium mt-4 leading-[1.7]">
          가죽 결과 스티치의 미세 텍스처가 개체의 지문입니다
        </p>
        <p className="text-base text-[var(--color-muted)] mt-2 leading-[1.8] max-w-[520px]">
          사진 한 장을 등록된 결 무늬와 대조해 어떤 고객의 어떤 물건인지 알아봅니다.
          식별된 개체의 컨디션이 그대로 상담의 근거가 돼요.
        </p>
      </div>

      {loadStatus === 'error' && <ErrorBanner message={loadError} onRetry={load} />}

      <div>
        {/* Ⅰ — 질의 이미지 선택 */}
        <div className="relative overflow-hidden min-h-[200px] border-t border-[var(--color-border)] py-14">
          <SectionNumeral>I</SectionNumeral>
          <div className="relative z-10 max-w-[520px]">
            <span className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)]">
              질의 이미지
            </span>

            {loadStatus === 'loading' && (
              <div className="grid grid-cols-4 gap-2 mt-5 animate-pulse">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="aspect-square bg-[var(--color-surface)]" />
                ))}
              </div>
            )}

            {loadStatus === 'ready' &&
              samples.map((sample) => (
                <div key={sample.asset_id} className="mt-5">
                  <p className="text-sm text-[var(--color-muted)]">
                    등록 개체{' '}
                    <span className="font-serif text-[var(--color-text)]">{sample.product_name}</span>
                    의 결 무늬로 시연하거나, 사진을 직접 올려보세요
                  </p>
                  <div className="grid grid-cols-4 gap-2 mt-3.5">
                    {sample.images.map((image) => (
                      <QueryThumb
                        key={image.path}
                        image={image}
                        selected={query?.kind === 'sample' && query.image.path === image.path}
                        onSelect={() => selectSample(sample, image)}
                      />
                    ))}
                  </div>
                </div>
              ))}

            <div className="mt-3.5">
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => selectUpload(e.target.files?.[0])}
              />
              <button
                onClick={() => fileRef.current?.click()}
                className={`w-full border border-dashed px-4 py-3.5 text-sm transition-colors duration-150 ${
                  query?.kind === 'upload'
                    ? 'border-[var(--color-accent)] text-[var(--color-text)]'
                    : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-accent)]/50 hover:text-[var(--color-text)]'
                }`}
              >
                {query?.kind === 'upload' ? `사진 선택됨 — ${query.name}` : '사진 올리기 (미등록 개체는 신규 등록을 안내해요)'}
              </button>
            </div>

            {query && (
              <div className="mt-6 flex items-end gap-5">
                {/* 선택된 질의 미리보기 + 판독 스캔라인 */}
                <div className="relative w-28 h-28 shrink-0 overflow-hidden border border-[var(--color-border)]">
                  {previewUrl ? (
                    <img src={previewUrl} alt="질의 이미지" className="absolute inset-0 w-full h-full object-cover" />
                  ) : (
                    <span className="absolute inset-0 flex items-center justify-center bg-[var(--color-surface)] text-[11px] text-[var(--color-muted)]">
                      질의 이미지
                    </span>
                  )}
                  {scanning && (
                    <span className="fp-scanline absolute left-0 right-0 h-[2px] bg-[var(--color-accent)] shadow-[0_0_10px_var(--color-accent)]" />
                  )}
                </div>
                <button
                  onClick={identify}
                  disabled={scanning}
                  className="bg-[var(--color-accent)] text-[var(--color-bg)] text-xs tracking-[0.16em] uppercase px-5 py-3 transition-opacity duration-150 hover:opacity-90 disabled:opacity-60"
                >
                  {scanning ? '결 무늬 대조 중…' : '이 이미지로 식별'}
                </button>
              </div>
            )}

            {matchError && (
              <div className="mt-5">
                <ErrorBanner message={matchError} onRetry={identify} />
              </div>
            )}
          </div>
        </div>

        {/* Ⅱ — 판독 결과 */}
        {result && (
          <div className="relative overflow-hidden min-h-[200px] border-t border-[var(--color-border)] py-14">
            <SectionNumeral>II</SectionNumeral>
            <div className="relative z-10 max-w-[520px]">
              <div className="flex items-baseline justify-between mb-5">
                <span className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)]">
                  판독 결과
                </span>
                <span className="text-[11px] tracking-[0.08em] text-[var(--color-muted)] tabular-nums">
                  유사도 {Math.round(result.similarity * 100)}% · 임계 {Math.round(result.threshold * 100)}%
                </span>
              </div>

              {result.is_match && matchedSample ? (
                <div className="space-y-7">
                  <p className="text-base leading-[1.8] text-[var(--color-text)]">
                    <span className="font-serif">{matchedSample.customer_name}</span>
                    {matchedSample.tier ? ` · ${matchedSample.tier}` : ''} 고객의 개체로
                    확인됐어요.
                  </p>
                  <CitationCard
                    citation={{
                      asset_id: matchedSample.asset_id,
                      product_name: matchedSample.product_name,
                      condition_score: matchedSample.condition_score,
                      next_service_months: matchedSample.next_service_months,
                      headline_finding: matchedSample.headline_finding,
                    }}
                  />
                  <button
                    onClick={() => navigate(`/chat?customer=${matchedSample.customer_id}`)}
                    className="bg-[var(--color-accent)] text-[var(--color-bg)] text-xs tracking-[0.16em] uppercase px-5 py-3 transition-opacity duration-150 hover:opacity-90"
                  >
                    이 고객으로 상담 시작
                  </button>
                </div>
              ) : result.is_match ? (
                /* 매칭됐지만 갤러리 메타에 없는 개체(전체 검색 등) — id 만이라도 보여준다 */
                <p className="text-base leading-[1.8] text-[var(--color-text)]">
                  등록 개체 <span className="font-serif">{result.matched_asset_id}</span> 로
                  확인됐어요.
                </p>
              ) : (
                <div className="space-y-4">
                  <p className="text-base leading-[1.8] text-[var(--color-text)]">
                    등록된 결 무늬 중 일치하는 개체가 없어요.
                  </p>
                  <p className="text-sm leading-[1.8] text-[var(--color-muted)]">
                    새 개체로 등록하면 다음 방문부터 이 물건의 컨디션을 근거로 상담할 수
                    있어요. 등록은 부티크에서 8개 부위 촬영으로 몇 분이면 끝나요.
                  </p>
                </div>
              )}

              {result.candidates?.length > 0 && (
                <div className="mt-8">
                  <span className="text-[11px] tracking-[0.18em] uppercase text-[var(--color-muted)]">
                    근접 후보
                  </span>
                  <ul className="mt-3.5 space-y-2.5">
                    {result.candidates.map((cand) => (
                      <li key={cand.asset_id} className="flex items-center gap-3">
                        <span className="w-20 shrink-0 text-xs text-[var(--color-muted)] tabular-nums">
                          {cand.asset_id}
                        </span>
                        <span className="relative flex-1 h-px bg-[var(--color-border)]">
                          <span
                            className="absolute left-0 top-[-0.75px] h-[2.5px] bg-[var(--color-accent)]"
                            style={{ width: `${Math.round(cand.similarity * 100)}%` }}
                          />
                        </span>
                        <span className="w-10 shrink-0 text-right text-xs text-[var(--color-muted)] tabular-nums">
                          {Math.round(cand.similarity * 100)}%
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

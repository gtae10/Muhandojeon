import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchProduct } from '../api/client.js'
import ConditionBadge from '../components/ConditionBadge.jsx'

export default function ProductScreen() {
  const { productId = 'demo' } = useParams()
  const [product, setProduct] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | error

  useEffect(() => {
    let cancelled = false
    setStatus('loading')

    fetchProduct(productId)
      .then((data) => {
        if (!cancelled) {
          setProduct(data)
          setStatus('ready')
        }
      })
      .catch(() => {
        // TODO(풀스택2 Backend) 연동 전까지는 목업 데이터로 화면 확인
        if (!cancelled) {
          setProduct({
            id: productId,
            name: 'MCM Aren Backpack',
            purchasedAt: '2023-05-12',
            conditionScore: 71,
            wearPoints: [{ part: '핸들', severity: '임계 근접' }],
          })
          setStatus('ready')
        }
      })

    return () => {
      cancelled = true
    }
  }, [productId])

  if (status === 'loading') {
    return <p className="text-sm text-[var(--color-muted)]">불러오는 중…</p>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-medium">{product.name}</h1>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          구매일 {product.purchasedAt}
        </p>
      </div>

      <ConditionBadge score={product.conditionScore} />

      {/* TODO(AI1 담당): wearPoints 실제 구조 확정되면 렌더링 방식 조정 */}
      <ul className="text-sm space-y-1">
        {product.wearPoints.map((w, i) => (
          <li key={i} className="flex justify-between border-b border-white/10 py-2">
            <span>{w.part}</span>
            <span className="text-[var(--color-accent)]">{w.severity}</span>
          </li>
        ))}
      </ul>

      <div className="flex gap-3 pt-4">
        <Link
          to={`/capture/${product.id}`}
          className="flex-1 text-center py-3 rounded-full border border-white/20 text-sm"
        >
          상태 재촬영
        </Link>
        <Link
          to={`/chat/${product.id}`}
          className="flex-1 text-center py-3 rounded-full bg-[var(--color-accent)] text-black text-sm"
        >
          상담 시작
        </Link>
      </div>
    </div>
  )
}

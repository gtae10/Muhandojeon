import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getHealth, connectionState } from '../api/client.js'

const POLL_MS = 5000

export default function Layout() {
  const location = useLocation()
  const [status, setStatus] = useState('checking') // checking | live | mock

  useEffect(() => {
    let cancelled = false

    async function poll() {
      // getHealth() 는 NetworkUnavailableError 만 목업으로 흡수한다. 헬스체크가 4xx/5xx(ApiError)를
      // 내더라도 서버는 응답한 것이므로(connectionState 는 이미 'live') 배지 갱신만 계속한다.
      await getHealth().catch(() => {})
      if (!cancelled) setStatus(connectionState.current)
    }

    poll()
    const timer = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-[var(--color-border)] px-6 py-4 flex items-center justify-between">
        <Link to="/" className="tracking-[0.2em] text-xs font-medium text-[var(--color-muted)]">
          LUXE CLIENTELING
        </Link>
        <div className="flex items-center gap-4 text-xs">
          <Link
            to="/consult"
            className={
              location.pathname === '/consult'
                ? 'text-[var(--color-accent)]'
                : 'text-[var(--color-muted)]'
            }
          >
            직접 상담
          </Link>
          <span className="flex items-center gap-1.5 text-[var(--color-muted)]">
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full ${
                status === 'checking'
                  ? 'bg-[var(--color-muted)]'
                  : status === 'live'
                    ? 'bg-emerald-500'
                    : 'bg-[var(--color-warn)]'
              }`}
            />
            {status === 'checking' ? '확인 중' : status === 'live' ? '서버 연결됨' : '목업 모드'}
          </span>
        </div>
      </header>

      <main className="flex-1 px-6 py-8 max-w-lg mx-auto w-full">
        <Outlet />
      </main>
    </div>
  )
}

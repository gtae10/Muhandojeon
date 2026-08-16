import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getHealth, isMockMode } from '../api/client.js'

export default function Layout() {
  const location = useLocation()
  const [status, setStatus] = useState('checking') // checking | live | mock

  useEffect(() => {
    getHealth().then(() => {
      setStatus(isMockMode.current ? 'mock' : 'live')
    })
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

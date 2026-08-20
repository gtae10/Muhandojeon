import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getHealth, connectionState } from '../api/client.js'
import Footer from './Footer.jsx'

const POLL_MS = 5000
const THEME_KEY = 'luxe-theme'

function readInitialTheme() {
  const stored = typeof window !== 'undefined' ? window.localStorage.getItem(THEME_KEY) : null
  return stored === 'light' ? 'light' : 'dark'
}

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <circle cx="8" cy="8" r="3.2" />
      <path d="M8 1.2v1.6M8 13.2v1.6M2.3 8H.8M15.2 8h-1.5M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" strokeLinecap="round" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <path d="M13.8 9.6A6 6 0 1 1 6.4 2.2a6.8 6.8 0 0 0 7.4 7.4z" strokeLinejoin="round" />
    </svg>
  )
}

export default function Layout() {
  const location = useLocation()
  const [status, setStatus] = useState('checking') // checking | live | mock
  const [theme, setTheme] = useState(readInitialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  useEffect(() => {
    let cancelled = false

    async function poll() {
      // getHealth() 는 NetworkUnavailableError 만 목업으로 흡수한다. 헬스체크가 4xx/5xx(ApiError)를
      // 내더라도 서버는 응답한 것이므로(connectionState 는 이미 'live') 배지 갱신만 계속한다.
      await getHealth().catch(() => {})
      if (!cancelled) setStatus(connectionState.current)
    }

    // 다른 화면의 실제 API 호출(예: /session/advise)이 폴백하면 다음 헬스체크 폴링을
    // 기다리지 않고 즉시 배지에 반영한다.
    const unsubscribe = connectionState.subscribe((next) => {
      if (!cancelled) setStatus(next)
    })

    poll()
    const timer = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      unsubscribe()
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-[var(--color-border)] px-4 sm:px-6 py-4 flex items-center justify-between gap-3">
        <Link to="/" className="flex items-center gap-2 sm:gap-2.5 min-w-0">
          <span className="w-[5px] h-[5px] rounded-full bg-[var(--color-accent)] shrink-0" />
          <span className="tracking-[0.16em] sm:tracking-[0.24em] text-sm sm:text-base font-semibold text-[var(--color-text)] whitespace-nowrap">
            LUXE CLIENTELING
          </span>
        </Link>
        <div className="flex items-center gap-3 sm:gap-5 text-xs shrink-0">
          <Link
            to="/identify"
            className={`font-display font-bold whitespace-nowrap text-sm sm:text-base ${
              location.pathname === '/identify'
                ? 'text-[var(--color-accent)]'
                : 'text-[var(--color-muted)] hover:text-[var(--color-accent)]'
            }`}
          >
            개체 식별
          </Link>
          <Link
            to="/consult"
            className={`font-display font-bold whitespace-nowrap text-sm sm:text-base ${
              location.pathname === '/consult'
                ? 'text-[var(--color-accent)]'
                : 'text-[var(--color-muted)] hover:text-[var(--color-accent)]'
            }`}
          >
            직접 상담
          </Link>
          <Link
            to="/chat"
            className={`font-display font-bold whitespace-nowrap text-sm sm:text-base ${
              location.pathname === '/chat'
                ? 'text-[var(--color-accent)]'
                : 'text-[var(--color-muted)] hover:text-[var(--color-accent)]'
            }`}
          >
            자유 상담
          </Link>
          <span
            className="flex items-center gap-1.5 text-[var(--color-muted)]"
            title={status === 'checking' ? '확인 중' : status === 'live' ? '서버 연결됨' : '목업 모드'}
          >
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                status === 'checking'
                  ? 'bg-[var(--color-muted)]'
                  : status === 'live'
                    ? 'bg-emerald-500'
                    : 'bg-[var(--color-warn)]'
              }`}
            />
            <span className="hidden sm:inline whitespace-nowrap">
              {status === 'checking' ? '확인 중' : status === 'live' ? '서버 연결됨' : '목업 모드'}
            </span>
          </span>
          <button
            onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            aria-label={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
            className="flex items-center justify-center w-6 h-6 border border-[var(--color-border)] text-[var(--color-muted)] transition-colors duration-150 hover:text-[var(--color-accent)] hover:border-[var(--color-accent)]/40"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </header>

      <main className="flex-1 px-6 py-12 max-w-[720px] mx-auto w-full">
        <Outlet />
      </main>

      <Footer />
    </div>
  )
}

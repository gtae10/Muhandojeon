import { Outlet, Link } from 'react-router-dom'

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <Link to="/" className="tracking-[0.2em] text-sm font-medium">
          MCM CONTINUUM
        </Link>
        {/* TODO(기획·디자인): 실제 네비게이션 항목/브랜드 톤 확정되면 교체 */}
        <nav className="flex gap-4 text-xs text-[var(--color-muted)]">
          <Link to="/capture">지문 등록</Link>
        </nav>
      </header>

      <main className="flex-1 px-6 py-8 max-w-md mx-auto w-full">
        <Outlet />
      </main>
    </div>
  )
}

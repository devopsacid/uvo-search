import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'
import { GlobalSearch } from '@/components/search/GlobalSearch'

const navItems = [
  { to: '/analytika', label: sk.nav.analytics, end: false },
  { to: '/firmy', label: sk.nav.firmy, end: false },
  { to: '/zakazky', label: sk.nav.zakazky, end: false },
  { to: '/graph', label: sk.nav.graph, end: false },
  { to: '/ingestion', label: sk.nav.ingestion, end: false },
  { to: '/about', label: sk.nav.about, end: false },
] as const

export function Header() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <span className="text-base font-semibold text-foreground">UVO</span>
        <GlobalSearch />
        <nav className="-mx-1 flex max-w-full gap-1 overflow-x-auto px-1 py-0.5" aria-label={sk.common.mainNavLabel}>
          {navItems.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}

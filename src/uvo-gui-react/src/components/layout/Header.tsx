import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

const navItems = [
  { to: '/', label: sk.nav.overview, end: true },
  { to: '/search', label: sk.nav.search, end: false },
  { to: '/suppliers', label: sk.nav.suppliers, end: false },
  { to: '/procurers', label: sk.nav.procurers, end: false },
  { to: '/graph', label: sk.nav.graph, end: false },
  { to: '/about', label: sk.nav.about, end: false },
] as const

export function Header() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <span className="text-base font-semibold text-foreground">UVO</span>
        <nav className="flex gap-1" aria-label="Hlavna navigacia">
          {navItems.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-1.5 text-sm transition-colors',
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

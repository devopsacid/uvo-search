import { Suspense } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AnalyticsFilterBar } from '@/components/analytics/AnalyticsFilterBar'
import { RouteFallback } from '@/components/layout/RouteFallback'
import { FILTER_KEYS } from '@/lib/analyticsFilters'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

const TABS = [
  { slug: 'prehlad', label: () => sk.analytics.tabs.prehlad },
  { slug: 'koncentracia', label: () => sk.analytics.tabs.koncentracia },
  { slug: 'cpv', label: () => sk.analytics.tabs.cpv },
  { slug: 'pokrytie', label: () => sk.analytics.tabs.pokrytie },
] as const

/** Shared frame of the four dashboards: title, definition hint, tabs and the sticky filter bar. */
export function AnalyticsLayout() {
  const location = useLocation()
  // Tabs carry the current filters so switching dashboards keeps the same slice of the market.
  const current = new URLSearchParams(location.search)
  const carried = new URLSearchParams()
  for (const key of FILTER_KEYS) {
    const v = current.get(key)
    if (v) carried.set(key, v)
  }
  const search = carried.toString() ? `?${carried.toString()}` : ''
  const showFilters = !location.pathname.endsWith('/pokrytie')

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-foreground">{sk.analytics.title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{sk.analytics.definitionHint}</p>
        <nav aria-label={sk.analytics.tabsLabel} className="mt-4 flex gap-1 overflow-x-auto border-b border-border">
          {TABS.map((tab) => (
            <NavLink
              key={tab.slug}
              to={{ pathname: `/analytika/${tab.slug}`, search: tab.slug === 'pokrytie' ? '' : search }}
              className={({ isActive }) =>
                cn(
                  '-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  isActive
                    ? 'border-primary font-medium text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )
              }
            >
              {tab.label()}
            </NavLink>
          ))}
        </nav>
      </header>

      {showFilters ? (
        <AnalyticsFilterBar />
      ) : (
        <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          {sk.analytics.pokrytie.noFilters}
        </p>
      )}

      <Suspense fallback={<RouteFallback />}>
        <Outlet />
      </Suspense>
    </div>
  )
}

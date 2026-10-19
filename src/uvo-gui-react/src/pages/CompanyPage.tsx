import { Suspense } from 'react'
import { useParams, Link, NavLink, Outlet } from 'react-router-dom'
import { useCompanyProfile } from '@/api/queries/companies'
import { RouteFallback } from '@/components/layout/RouteFallback'
import { Skeleton } from '@/components/ui/Skeleton'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

const ROLE_LABELS: Record<string, string> = {
  supplier: sk.company.roleSupplier,
  procurer: sk.company.roleProcurer,
}

function RoleBadge({ role }: { role: string }) {
  const isSupplier = role === 'supplier'
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        isSupplier
          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
          : 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
      )}
    >
      {ROLE_LABELS[role] ?? role}
    </span>
  )
}

export function CompanyPage() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''

  const { data: profile, isLoading, isError, error } = useCompanyProfile(safeIco)

  const is404 = isError && (error as { status?: number })?.status === 404

  if (is404) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="text-lg font-medium text-foreground">{sk.company.notFound}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {sk.company.notFoundDetail.replace('{ico}', safeIco)}
        </p>
        <Link
          to="/companies"
          className="mt-6 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
        >
          {sk.company.notFoundAction}
        </Link>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="py-12 text-center">
        <p className="text-muted-foreground">{sk.common.error}</p>
        <Link to="/companies" className="mt-4 block text-sm text-primary hover:underline">
          ← {sk.common.back}
        </Link>
      </div>
    )
  }

  const tabs = [
    { to: `/company/${safeIco}/overview`, label: sk.company.tabOverview },
    { to: `/company/${safeIco}/contracts`, label: sk.company.tabContracts },
    { to: `/company/${safeIco}/network`, label: sk.company.tabNetwork },
    { to: `/company/${safeIco}/partners`, label: sk.company.tabPartners },
    { to: `/company/${safeIco}/cpv`, label: sk.company.tabCpv },
  ]

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div className="text-sm text-muted-foreground">
        <Link to="/companies" className="hover:underline">
          {sk.company.breadcrumbCompanies}
        </Link>
        <span className="mx-1.5">›</span>
        <span>{isLoading ? safeIco : (profile?.name ?? safeIco)}</span>
      </div>

      {/* Company header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1">
          {isLoading ? (
            <Skeleton className="h-7 w-64" />
          ) : (
            <h1 className="text-xl font-semibold text-foreground">{profile?.name}</h1>
          )}
          <p className="mt-1 text-sm text-muted-foreground">{sk.common.ico}: {safeIco}</p>
        </div>
        {!isLoading && profile?.roles && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {profile.roles.map((r) => (
              <RoleBadge key={r} role={r} />
            ))}
          </div>
        )}
      </div>

      {/* Tab strip */}
      <nav className="flex gap-1 border-b border-border pb-0" aria-label={sk.company.sectionsLabel}>
        {tabs.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'rounded-t-md px-3 py-1.5 text-sm transition-colors',
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

      {/* Sub-route content */}
      <Suspense fallback={<RouteFallback />}>
        <Outlet />
      </Suspense>
    </div>
  )
}

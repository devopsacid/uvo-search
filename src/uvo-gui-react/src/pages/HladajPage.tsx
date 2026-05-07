import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useUnifiedSearch } from '@/api/queries/unifiedSearch'
import { cn, formatCurrency } from '@/lib/utils'
import sk from '@/i18n/sk'

const ROLE_LABELS: Record<string, string> = {
  supplier: sk.firma.roleSupplier,
  procurer: sk.firma.roleProcurer,
}

const ICO_PATTERN = /^\d{8}$/

function defaultTab(q: string): 'firmy' | 'zakazky' {
  return ICO_PATTERN.test(q.trim()) ? 'firmy' : 'zakazky'
}

export function HladajPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const q = searchParams.get('q') ?? ''
  const tab = (searchParams.get('tab') as 'firmy' | 'zakazky' | null) ?? defaultTab(q)

  const { data, isFetching } = useUnifiedSearch(q)

  function handleQueryChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set('q', value)
      } else {
        next.delete('q')
      }
      return next
    }, { replace: true })
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && q.trim()) {
      // Reload same page with current q — already reflected in URL
      navigate(`/hladaj?q=${encodeURIComponent(q.trim())}`, { replace: true })
    }
  }

  function setTab(t: 'firmy' | 'zakazky') {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', t)
      return next
    }, { replace: true })
  }

  const firmy = data?.firmy ?? []
  const zakazky = data?.zakazky ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <h1 className="text-2xl font-semibold text-foreground">{sk.hladaj.title}</h1>

      {/* Search input */}
      <input
        autoFocus
        type="search"
        value={q}
        onChange={handleQueryChange}
        onKeyDown={handleKeyDown}
        placeholder={sk.globalSearch.placeholder}
        className="w-full rounded-lg border border-input bg-background px-4 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />

      {/* Empty-query state */}
      {!q && (
        <p className="text-sm text-muted-foreground">{sk.hladaj.emptyPrompt}</p>
      )}

      {/* Results */}
      {q.length >= 2 && (
        <>
          {/* Tab strip */}
          <div className="flex gap-1 border-b border-border">
            {(['firmy', 'zakazky'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  'px-4 py-2 text-sm font-medium transition-colors',
                  tab === t
                    ? 'border-b-2 border-primary text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t === 'firmy' ? sk.hladaj.tabFirmy : sk.hladaj.tabZakazky}
              </button>
            ))}
          </div>

          {/* Loading shimmer */}
          {isFetching && !data && (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg bg-muted" />
              ))}
            </div>
          )}

          {/* Firmy tab */}
          {tab === 'firmy' && !isFetching && (
            firmy.length === 0 ? (
              <NoResults q={q} />
            ) : (
              <ul className="space-y-2">
                {firmy.map((f) => (
                  <li key={f.ico}>
                    <Link
                      to={`/firma/${f.ico}`}
                      className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3 hover:bg-accent"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">{f.name}</p>
                        <p className="text-xs text-muted-foreground">IČO {f.ico}</p>
                      </div>
                      <div className="ml-4 flex shrink-0 items-center gap-2">
                        {f.roles.map((r) => (
                          <RoleBadge key={r} role={r} />
                        ))}
                        <span className="text-xs text-muted-foreground">
                          {f.contract_count} zákaziek
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )
          )}

          {/* Zákazky tab */}
          {tab === 'zakazky' && !isFetching && (
            zakazky.length === 0 ? (
              <NoResults q={q} />
            ) : (
              <ul className="space-y-2">
                {zakazky.map((z) => (
                  <li key={z.id}>
                    <Link
                      to={`/zakazky?selected=${z.id}`}
                      className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3 hover:bg-accent"
                    >
                      <div className="min-w-0">
                        <p className="line-clamp-2 text-sm font-medium text-foreground">{z.title}</p>
                        {z.procurer_name && (
                          <p className="truncate text-xs text-muted-foreground">{z.procurer_name}</p>
                        )}
                      </div>
                      <div className="ml-4 shrink-0 text-right">
                        {z.value != null && (
                          <p className="text-sm tabular-nums text-foreground">{formatCurrency(z.value)}</p>
                        )}
                        {z.year && (
                          <p className="text-xs text-muted-foreground">{z.year}</p>
                        )}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )
          )}
        </>
      )}
    </div>
  )
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

function NoResults({ q }: { q: string }) {
  return (
    <p className="text-sm text-muted-foreground">
      {sk.hladaj.noResults.replace('{q}', q)}
    </p>
  )
}

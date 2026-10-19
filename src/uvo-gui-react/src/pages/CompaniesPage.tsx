import { Link, useSearchParams } from 'react-router-dom'
import { useCompaniesList } from '@/api/queries/companies'
import { Sidebar, SidebarSection } from '@/components/layout/Sidebar'
import { FilterInput } from '@/components/search/FilterBar'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { SkeletonRow } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

const PAGE_SIZE = 20

const ROLE_CHIPS: { value: string; label: string }[] = [
  { value: 'all', label: sk.companies.chipAll },
  { value: 'supplier', label: sk.companies.chipSupplier },
  { value: 'procurer', label: sk.companies.chipProcurer },
]

export function CompaniesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const q = searchParams.get('q') ?? ''
  const role = searchParams.get('role') ?? 'all'
  const page = Number(searchParams.get('page') ?? '1')

  function setParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set(key, value)
      } else {
        next.delete(key)
      }
      if (key !== 'page') next.delete('page')
      return next
    }, { replace: false })
  }

  const { data, isLoading, isError } = useCompaniesList({
    q,
    role,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const hasFilters = !!q || role !== 'all'

  return (
    <div className="flex gap-4">
      <Sidebar>
        <SidebarSection title={sk.companies.title}>
          <FilterInput
            label={sk.common.searchAction}
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder={sk.companies.searchPlaceholder}
          />
          <div className="mt-3 flex flex-wrap gap-1.5">
            {ROLE_CHIPS.map((chip) => (
              <button
                key={chip.value}
                onClick={() => setParam('role', chip.value === 'all' ? '' : chip.value)}
                className={
                  role === chip.value || (chip.value === 'all' && !searchParams.get('role'))
                    ? 'rounded-full px-2.5 py-0.5 text-xs font-medium bg-primary text-primary-foreground'
                    : 'rounded-full px-2.5 py-0.5 text-xs font-medium border border-border text-muted-foreground hover:bg-accent'
                }
              >
                {chip.label}
              </button>
            ))}
          </div>
        </SidebarSection>
        {hasFilters && (
          <button
            onClick={() => {
              setSearchParams({}, { replace: false })
            }}
            className="mt-3 w-full rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent"
          >
            {sk.common.clearFilters}
          </button>
        )}
      </Sidebar>

      <div className="min-w-0 flex-1">
        <h1 className="mb-4 text-lg font-semibold text-foreground">{sk.companies.title}</h1>

        {isError && (
          <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
            {sk.common.error}
          </div>
        )}

        {isLoading ? (
          <div className="rounded-lg border border-border bg-card">
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>{sk.companies.colName}</TableHead>
                  <TableHead>{sk.companies.colIco}</TableHead>
                  <TableHead>{sk.companies.colRole}</TableHead>
                  <TableHead>{sk.companies.colContracts}</TableHead>
                  <TableHead>{sk.companies.colValue}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {Array.from({ length: 10 }).map((_, i) => (
                  <SkeletonRow key={i} cols={5} />
                ))}
              </TableBody>
            </Table>
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            title={sk.companies.noResults}
            description={sk.companies.noResultsHint}
            action={
              hasFilters ? (
                <button
                  onClick={() => setSearchParams({}, { replace: false })}
                  className="text-sm text-primary hover:underline"
                >
                  {sk.common.clearFilters}
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="rounded-lg border border-border bg-card">
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>{sk.companies.colName}</TableHead>
                  <TableHead>{sk.companies.colIco}</TableHead>
                  <TableHead>{sk.companies.colRole}</TableHead>
                  <TableHead className="text-right">{sk.companies.colContracts}</TableHead>
                  <TableHead className="text-right">{sk.companies.colValue}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {items.map((row) => (
                  <TableRow key={row.ico}>
                    <TableCell>
                      <Link
                        to={`/company/${row.ico}`}
                        className="text-primary hover:underline"
                      >
                        {row.name}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{row.ico}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {row.roles.includes('supplier') && (
                          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                            DOD
                          </span>
                        )}
                        {row.roles.includes('procurer') && (
                          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                            OBS
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumber(row.contract_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCurrency(row.total_value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="border-t border-border px-3">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={total}
                onPageChange={(p) => setParam('page', String(p))}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

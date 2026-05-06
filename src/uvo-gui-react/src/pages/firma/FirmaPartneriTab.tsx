import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useFirmaPartneri } from '@/api/queries/firma'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { SkeletonRow } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatCurrency } from '@/lib/utils'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

type Role = 'all' | 'supplier' | 'procurer'
type Sort = 'value' | 'count'

const PAGE_SIZE = 25

const CHIPS: { role: Role; label: string }[] = [
  { role: 'all', label: sk.firma.chipAll },
  { role: 'supplier', label: sk.firma.chipAsSupplier },
  { role: 'procurer', label: sk.firma.chipAsProcurer },
]

const ROLE_LABELS: Record<string, string> = {
  supplier: sk.firma.roleSupplier,
  procurer: sk.firma.roleProcurer,
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

export function FirmaPartneriTab() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''
  const [searchParams, setSearchParams] = useSearchParams()

  const role = (searchParams.get('role') as Role) ?? 'all'
  const sort = (searchParams.get('sort') as Sort) ?? 'value'
  const page = Number(searchParams.get('page') ?? '1')

  function setRole(r: Role) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (r === 'all') {
          next.delete('role')
        } else {
          next.set('role', r)
        }
        next.delete('page')
        return next
      },
      { replace: false },
    )
  }

  function setSort(s: Sort) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (s === 'value') {
          next.delete('sort')
        } else {
          next.set('sort', s)
        }
        next.delete('page')
        return next
      },
      { replace: false },
    )
  }

  function setPage(p: number) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('page', String(p))
        return next
      },
      { replace: false },
    )
  }

  const offset = (page - 1) * PAGE_SIZE

  const { data, isLoading, isError } = useFirmaPartneri(safeIco, {
    role,
    sort,
    limit: PAGE_SIZE,
    offset,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="space-y-3">
      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Role chips */}
        <div className="flex gap-2">
          {CHIPS.map(({ role: r, label }) => (
            <button
              key={r}
              onClick={() => setRole(r)}
              className={cn(
                'rounded-full px-3 py-1 text-sm transition-colors',
                r === role
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border text-muted-foreground hover:bg-accent',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Sort selector */}
        <div className="ml-auto flex gap-1">
          <button
            onClick={() => setSort('value')}
            className={cn(
              'rounded px-3 py-1 text-sm transition-colors',
              sort === 'value'
                ? 'bg-primary text-primary-foreground'
                : 'border border-border text-muted-foreground hover:bg-accent',
            )}
          >
            {sk.firma.sortByValue}
          </button>
          <button
            onClick={() => setSort('count')}
            className={cn(
              'rounded px-3 py-1 text-sm transition-colors',
              sort === 'count'
                ? 'bg-primary text-primary-foreground'
                : 'border border-border text-muted-foreground hover:bg-accent',
            )}
          >
            {sk.firma.sortByCount}
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
          {sk.common.error}
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <tr>
                <TableHead>{sk.firma.colPartner}</TableHead>
                <TableHead>{sk.firma.colRola}</TableHead>
                <TableHead className="text-right">{sk.firma.colZakazky}</TableHead>
                <TableHead className="text-right">{sk.firma.colHodnota}</TableHead>
                <TableHead>{sk.firma.colPosledna}</TableHead>
              </tr>
            </TableHeader>
            <TableBody>
              {Array.from({ length: 8 }).map((_, i) => (
                <SkeletonRow key={i} cols={5} />
              ))}
            </TableBody>
          </Table>
        </div>
      ) : items.length === 0 ? (
        <EmptyState title={sk.firma.partneriEmpty} description={sk.firma.partneriEmptyHint} />
      ) : (
        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <tr>
                <TableHead>{sk.firma.colPartner}</TableHead>
                <TableHead>{sk.firma.colRola}</TableHead>
                <TableHead className="text-right">{sk.firma.colZakazky}</TableHead>
                <TableHead className="text-right">{sk.firma.colHodnota}</TableHead>
                <TableHead>{sk.firma.colPosledna}</TableHead>
              </tr>
            </TableHeader>
            <TableBody>
              {items.map((row, i) => (
                <TableRow key={row.ico ?? `row-${i}`}>
                  <TableCell className="max-w-xs">
                    {row.ico ? (
                      <Link
                        to={`/firma/${row.ico}`}
                        className="text-primary hover:underline line-clamp-2"
                      >
                        {row.name ?? row.ico}
                      </Link>
                    ) : (
                      <span className="line-clamp-2">{row.name ?? '—'}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <RoleBadge role={row.role} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{row.contract_count}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCurrency(row.total_value)}
                  </TableCell>
                  <TableCell>
                    {row.last_contract_at
                      ? new Date(row.last_contract_at).toLocaleDateString('sk-SK')
                      : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="border-t border-border px-3">
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
          </div>
        </div>
      )}
    </div>
  )
}

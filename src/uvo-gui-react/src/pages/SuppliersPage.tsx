import { useSearchParams } from 'react-router-dom'
import { useSuppliers } from '@/api/queries/suppliers'
import { Sidebar, SidebarSection } from '@/components/layout/Sidebar'
import { FilterInput } from '@/components/search/FilterBar'
import { EntityLink } from '@/components/entity/EntityLink'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { SkeletonRow } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

const PAGE_SIZE = 20

export function SuppliersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const q = searchParams.get('q') ?? ''
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

  const { data, isLoading, isError } = useSuppliers({
    q: q || undefined,
    page,
    page_size: PAGE_SIZE,
  })

  const suppliers = data?.data ?? []
  const total = data?.pagination.total ?? 0

  return (
    <div className="flex gap-4">
      <Sidebar>
        <SidebarSection title={sk.suppliers.title}>
          <FilterInput
            label="Hľadať"
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder={sk.suppliers.searchPlaceholder}
          />
        </SidebarSection>
        {q && (
          <button
            onClick={() => setParam('q', '')}
            className="mt-3 w-full rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent"
          >
            {sk.common.clearFilters}
          </button>
        )}
      </Sidebar>

      <div className="min-w-0 flex-1">
        <h1 className="mb-4 text-lg font-semibold text-foreground">{sk.suppliers.title}</h1>

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
                  <TableHead>{sk.suppliers.colName}</TableHead>
                  <TableHead>{sk.suppliers.colIco}</TableHead>
                  <TableHead>{sk.suppliers.colContracts}</TableHead>
                  <TableHead>{sk.suppliers.colValue}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {Array.from({ length: 10 }).map((_, i) => (
                  <SkeletonRow key={i} cols={4} />
                ))}
              </TableBody>
            </Table>
          </div>
        ) : suppliers.length === 0 ? (
          <EmptyState
            title={sk.suppliers.noResults}
            description={sk.suppliers.noResultsHint}
            action={
              q ? (
                <button
                  onClick={() => setParam('q', '')}
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
                  <TableHead>{sk.suppliers.colName}</TableHead>
                  <TableHead>{sk.suppliers.colIco}</TableHead>
                  <TableHead className="text-right">{sk.suppliers.colContracts}</TableHead>
                  <TableHead className="text-right">{sk.suppliers.colValue}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {suppliers.map((s) => (
                  <TableRow key={s.ico}>
                    <TableCell>
                      <EntityLink ico={s.ico} name={s.name} type="supplier" />
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{s.ico}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumber(s.contract_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCurrency(s.total_value)}</TableCell>
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

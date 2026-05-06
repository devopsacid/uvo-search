import { useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useCompanyPin } from '@/context/CompanyPinContext'
import { useProcurers } from '@/api/queries/procurers'
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

export function ProcurersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')

  const { ico, type } = useCompanyPin()
  const navigate = useNavigate()

  useEffect(() => {
    if (ico && type === 'procurer') {
      navigate(`/procurers/${ico}`, { replace: true })
    }
  }, [ico, type, navigate])

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

  const { data, isLoading, isError } = useProcurers({
    q: q || undefined,
    page,
    page_size: PAGE_SIZE,
  })

  const procurers = data?.data ?? []
  const total = data?.pagination.total ?? 0

  return (
    <div className="flex gap-4">
      <Sidebar>
        <SidebarSection title={sk.procurers.title}>
          <FilterInput
            label="Hľadať"
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder={sk.procurers.searchPlaceholder}
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
        <h1 className="mb-4 text-lg font-semibold text-foreground">{sk.procurers.title}</h1>

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
                  <TableHead>{sk.procurers.colName}</TableHead>
                  <TableHead>{sk.procurers.colIco}</TableHead>
                  <TableHead>{sk.procurers.colContracts}</TableHead>
                  <TableHead>{sk.procurers.colSpend}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {Array.from({ length: 10 }).map((_, i) => (
                  <SkeletonRow key={i} cols={4} />
                ))}
              </TableBody>
            </Table>
          </div>
        ) : procurers.length === 0 ? (
          <EmptyState
            title={sk.procurers.noResults}
            description={sk.procurers.noResultsHint}
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
                  <TableHead>{sk.procurers.colName}</TableHead>
                  <TableHead>{sk.procurers.colIco}</TableHead>
                  <TableHead className="text-right">{sk.procurers.colContracts}</TableHead>
                  <TableHead className="text-right">{sk.procurers.colSpend}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {procurers.map((p) => (
                  <TableRow key={p.ico}>
                    <TableCell>
                      <EntityLink ico={p.ico} name={p.name} type="procurer" />
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{p.ico}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumber(p.contract_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCurrency(p.total_spend)}</TableCell>
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

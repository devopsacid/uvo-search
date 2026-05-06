import { useSearchParams } from 'react-router-dom'
import { useContractSearch, useContractDetail } from '@/api/queries/contracts'
import { Sidebar, SidebarSection } from '@/components/layout/Sidebar'
import { EntityAutocomplete } from '@/components/search/EntityAutocomplete'
import { FilterInput } from '@/components/search/FilterBar'
import { EntityLink } from '@/components/entity/EntityLink'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Skeleton, SkeletonRow } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatCurrency } from '@/lib/utils'
import sk from '@/i18n/sk'

const PAGE_SIZE = 20

const YEAR_OPTIONS = Array.from({ length: 15 }, (_, i) => {
  const y = String(2024 - i)
  return { value: y, label: y }
})

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const q = searchParams.get('q') ?? ''
  const year = searchParams.get('year') ?? ''
  const cpv = searchParams.get('cpv') ?? ''
  const procurer_ico = searchParams.get('procurer_ico') ?? ''
  const supplier_ico = searchParams.get('supplier_ico') ?? ''
  const page = Number(searchParams.get('page') ?? '1')
  const selectedId = searchParams.get('selected') ?? ''

  function setParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set(key, value)
      } else {
        next.delete(key)
      }
      if (key !== 'page' && key !== 'selected') next.delete('page')
      return next
    }, { replace: false })
  }

  function selectContract(id: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (next.get('selected') === id) {
        next.delete('selected')
      } else {
        next.set('selected', id)
      }
      return next
    }, { replace: true })
  }

  function clearFilters() {
    setSearchParams({}, { replace: false })
  }

  // Build date_from/date_to from year
  const date_from = year ? `${year}-01-01` : undefined
  const date_to = year ? `${year}-12-31` : undefined

  const { data, isLoading, isError, error } = useContractSearch({
    q: q || undefined,
    cpv: cpv || undefined,
    date_from,
    date_to,
    ico: supplier_ico || undefined,
    page,
    page_size: PAGE_SIZE,
  })

  const { data: detail, isLoading: detailLoading } = useContractDetail(selectedId)

  const contracts = data?.data ?? []
  const total = data?.pagination.total ?? 0
  const hasFilters = !!(q || year || cpv || procurer_ico || supplier_ico)

  return (
    <div className="flex gap-4">
      {/* Filter sidebar */}
      <Sidebar>
        <div className="space-y-4">
          <SidebarSection title={sk.search.title}>
            <FilterInput
              label={sk.search.filterQ}
              value={q}
              onChange={(e) => setParam('q', e.target.value)}
              placeholder={sk.search.placeholder}
            />
          </SidebarSection>

          <SidebarSection>
            <label className="block space-y-1">
              <span className="text-xs text-muted-foreground">{sk.search.filterYear}</span>
              <select
                value={year}
                onChange={(e) => setParam('year', e.target.value)}
                className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Všetky</option>
                {YEAR_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
          </SidebarSection>

          <SidebarSection>
            <FilterInput
              label={sk.search.filterCpv}
              value={cpv}
              onChange={(e) => setParam('cpv', e.target.value)}
              placeholder="napr. 45000000"
            />
          </SidebarSection>

          <SidebarSection>
            <FilterInput
              label={sk.search.filterSupplier}
              value={supplier_ico}
              onChange={(e) => setParam('supplier_ico', e.target.value)}
              placeholder="IČO"
            />
          </SidebarSection>

          {hasFilters && (
            <button
              onClick={clearFilters}
              className="w-full rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent"
            >
              {sk.common.clearFilters}
            </button>
          )}
        </div>
      </Sidebar>

      {/* Results */}
      <div className="min-w-0 flex-1">
        <div className="mb-4">
          <EntityAutocomplete
            onSelect={(ico, type) => {
              if (type === 'supplier') setParam('supplier_ico', ico)
              else setParam('procurer_ico', ico)
            }}
          />
        </div>

        {isError && (
          <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
            {sk.common.error}: {error instanceof Error ? error.message : ''}
          </div>
        )}

        {isLoading ? (
          <div className="rounded-lg border border-border bg-card">
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>{sk.search.colTitle}</TableHead>
                  <TableHead>{sk.search.colProcurer}</TableHead>
                  <TableHead>{sk.search.colSupplier}</TableHead>
                  <TableHead>{sk.search.colValue}</TableHead>
                  <TableHead>{sk.search.colYear}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {Array.from({ length: 8 }).map((_, i) => (
                  <SkeletonRow key={i} cols={5} />
                ))}
              </TableBody>
            </Table>
          </div>
        ) : contracts.length === 0 ? (
          <EmptyState
            title={sk.search.noResults}
            description={sk.search.noResultsHint}
            action={
              hasFilters ? (
                <button
                  onClick={clearFilters}
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
                  <TableHead>{sk.search.colTitle}</TableHead>
                  <TableHead>{sk.search.colProcurer}</TableHead>
                  <TableHead>{sk.search.colSupplier}</TableHead>
                  <TableHead className="text-right">{sk.search.colValue}</TableHead>
                  <TableHead>{sk.search.colYear}</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {contracts.map((c) => (
                  <TableRow
                    key={c.id}
                    onClick={() => selectContract(c.id)}
                    selected={c.id === selectedId}
                  >
                    <TableCell className="max-w-xs">
                      <span className="line-clamp-2 text-sm">{c.title}</span>
                    </TableCell>
                    <TableCell>
                      {c.procurer_ico ? (
                        <EntityLink ico={c.procurer_ico} name={c.procurer_name} type="procurer" />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {c.supplier_ico ? (
                        <EntityLink ico={c.supplier_ico} name={c.supplier_name ?? ''} type="supplier" />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(c.value)}
                    </TableCell>
                    <TableCell>{c.year || '—'}</TableCell>
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

      {/* Detail pane */}
      {selectedId && (
        <div className="w-96 shrink-0">
          <div className="sticky top-4 rounded-lg border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-semibold text-foreground">{sk.search.detailTitle}</h2>
            {detailLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-5 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : detail ? (
              <ContractDetailPane detail={detail} />
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}

import type { ContractDetail } from '@/api/types'

function ContractDetailPane({ detail }: { detail: ContractDetail }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="font-medium leading-snug text-foreground">{detail.title}</p>

      <dl className="space-y-1.5 text-sm">
        <Row label={sk.search.colProcurer}>
          {detail.procurer_ico ? (
            <EntityLink ico={detail.procurer_ico} name={detail.procurer_name} type="procurer" />
          ) : detail.procurer_name || '—'}
        </Row>
        <Row label={sk.search.colSupplier}>
          {detail.supplier_ico ? (
            <EntityLink ico={detail.supplier_ico} name={detail.supplier_name ?? ''} type="supplier" />
          ) : detail.supplier_name || '—'}
        </Row>
        <Row label={sk.search.colValue}>{formatCurrency(detail.value)}</Row>
        <Row label={sk.search.colYear}>{String(detail.year)}</Row>
        {detail.cpv_code && <Row label={sk.search.colCpv}>{detail.cpv_code}</Row>}
        {detail.publication_date && (
          <Row label={sk.search.labelPublished}>{detail.publication_date}</Row>
        )}
        <Row label={sk.search.labelId}>
          <span className="font-mono text-xs text-muted-foreground">{detail.id}</span>
        </Row>
      </dl>

      {detail.all_suppliers.length > 1 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">{sk.search.labelAllSuppliers}</p>
          <ul className="space-y-1">
            {detail.all_suppliers.map((s, i) => {
              const ico = String((s as Record<string, unknown>).ico ?? '')
              const name = String((s as Record<string, unknown>).name ?? '')
              return (
                <li key={i}>
                  {ico ? (
                    <EntityLink ico={ico} name={name} type="supplier" />
                  ) : (
                    <span>{name}</span>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="w-28 shrink-0 text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1 text-foreground">{children}</dd>
    </div>
  )
}

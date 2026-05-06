import { useParams, useSearchParams } from 'react-router-dom'
import { useContractSearch, useContractDetail } from '@/api/queries/contracts'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { SkeletonRow } from '@/components/ui/Skeleton'
import { Skeleton } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'
import { EmptyState } from '@/components/ui/EmptyState'
import { EntityLink } from '@/components/entity/EntityLink'
import { formatCurrency } from '@/lib/utils'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

type Role = 'all' | 'supplier' | 'procurer'

const PAGE_SIZE = 20

const CHIPS: { role: Role; label: string }[] = [
  { role: 'all', label: sk.firma.chipAll },
  { role: 'supplier', label: sk.firma.chipAsSupplier },
  { role: 'procurer', label: sk.firma.chipAsProcurer },
]

export function FirmaZakazkyTab() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''
  const [searchParams, setSearchParams] = useSearchParams()

  const role = (searchParams.get('role') as Role) ?? 'all'
  const page = Number(searchParams.get('page') ?? '1')
  const selectedId = searchParams.get('selected') ?? ''

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
        next.delete('selected')
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

  function selectContract(id: string) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (next.get('selected') === id) {
          next.delete('selected')
        } else {
          next.set('selected', id)
        }
        return next
      },
      { replace: true },
    )
  }

  const filters =
    role === 'supplier'
      ? { supplier_ico: safeIco }
      : role === 'procurer'
        ? { procurer_ico: safeIco }
        : { ico: safeIco }

  const { data, isLoading, isError } = useContractSearch({
    ...filters,
    page,
    page_size: PAGE_SIZE,
  })

  const { data: detail, isLoading: detailLoading } = useContractDetail(selectedId)

  const contracts = data?.data ?? []
  const total = data?.pagination.total ?? 0

  return (
    <div className="flex gap-4">
      <div className="min-w-0 flex-1 space-y-3">
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
                  <TableHead>{sk.search.colTitle}</TableHead>
                  <TableHead>{sk.search.colProcurer}</TableHead>
                  <TableHead>{sk.search.colSupplier}</TableHead>
                  <TableHead className="text-right">{sk.search.colValue}</TableHead>
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
          <EmptyState title={sk.firma.zakazkyEmpty} description={sk.firma.zakazkyEmptyHint} />
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
                onPageChange={setPage}
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
          ) : (
            detail.procurer_name || '—'
          )}
        </Row>
        <Row label={sk.search.colSupplier}>
          {detail.supplier_ico ? (
            <EntityLink ico={detail.supplier_ico} name={detail.supplier_name ?? ''} type="supplier" />
          ) : (
            detail.supplier_name || '—'
          )}
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

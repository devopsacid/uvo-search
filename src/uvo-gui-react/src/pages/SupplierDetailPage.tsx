import { useParams, Link } from 'react-router-dom'
import { BarChart3 } from 'lucide-react'
import { useSupplier, useSupplierSummary } from '@/api/queries/suppliers'
import { EntityLink } from '@/components/entity/EntityLink'
import { SpendByYearChart } from '@/components/charts/SpendByYearChart'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Skeleton, SkeletonRow } from '@/components/ui/Skeleton'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  )
}

export function SupplierDetailPage() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''

  const { data: detail, isLoading: detailLoading, isError: detailError } = useSupplier(safeIco)
  const { data: summary, isLoading: summaryLoading } = useSupplierSummary(safeIco)

  if (detailError) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">{sk.common.error}</p>
        <Link to="/suppliers" className="mt-4 block text-sm text-primary hover:underline">
          {sk.common.back}
        </Link>
      </div>
    )
  }

  const isLoading = detailLoading || summaryLoading

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          {isLoading ? (
            <>
              <Skeleton className="h-7 w-64 mb-2" />
              <Skeleton className="h-4 w-32" />
            </>
          ) : (
            <>
              <h1 className="text-xl font-semibold text-foreground">{detail?.name}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {sk.suppliers.ico}: {safeIco}
                {detail?.years_active && detail.years_active.length > 0 && (
                  <span className="ml-3">
                    {sk.suppliers.yearsActive}: {detail.years_active[0]}–{detail.years_active[detail.years_active.length - 1]}
                  </span>
                )}
              </p>
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Link
            to={`/analytics/supplier/${safeIco}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            <BarChart3 className="h-4 w-4" />
            Analyza
          </Link>
          <Link
            to="/suppliers"
            className="text-sm text-muted-foreground hover:text-foreground hover:underline"
          >
            ← {sk.common.back}
          </Link>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-4">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />
          ))
        ) : (
          <>
            <KpiCard
              label={sk.suppliers.kpiContracts}
              value={formatNumber(detail?.contract_count ?? 0)}
            />
            <KpiCard
              label={sk.suppliers.kpiTotal}
              value={formatCurrency(detail?.total_value ?? 0)}
            />
            <KpiCard
              label={sk.suppliers.kpiAvg}
              value={formatCurrency(detail?.avg_value ?? 0)}
            />
          </>
        )}
      </div>

      {/* Spend by year chart */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">{sk.suppliers.sectionSpend}</h2>
        {summaryLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <SpendByYearChart data={summary?.spend_by_year ?? []} />
        )}
      </div>

      {/* Top procurers */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">{sk.suppliers.sectionProcurers}</h2>
        </div>
        <Table>
          <TableHeader>
            <tr>
              <TableHead>{sk.procurers.colName}</TableHead>
              <TableHead className="text-right">{sk.suppliers.kpiContracts}</TableHead>
              <TableHead className="text-right">{sk.suppliers.kpiTotal}</TableHead>
            </tr>
          </TableHeader>
          <TableBody>
            {detailLoading
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={3} />)
              : detail?.top_procurers.map((p) => (
                  <TableRow key={p.ico}>
                    <TableCell>
                      <EntityLink ico={p.ico} name={p.name} type="procurer" />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumber(p.contract_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCurrency(p.total_value)}</TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>

      {/* Contracts table */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">{sk.suppliers.sectionContracts}</h2>
        </div>
        <Table>
          <TableHeader>
            <tr>
              <TableHead>{sk.search.colTitle}</TableHead>
              <TableHead>{sk.search.colProcurer}</TableHead>
              <TableHead className="text-right">{sk.search.colValue}</TableHead>
              <TableHead>{sk.search.colYear}</TableHead>
            </tr>
          </TableHeader>
          <TableBody>
            {detailLoading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} cols={4} />)
              : detail?.contracts.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="max-w-xs">
                      <span className="line-clamp-2 text-sm">{c.title}</span>
                    </TableCell>
                    <TableCell>
                      {c.procurer_ico ? (
                        <EntityLink ico={c.procurer_ico} name={c.procurer_name} type="procurer" />
                      ) : (
                        <span className="text-muted-foreground">{c.procurer_name || '—'}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatCurrency(c.value)}</TableCell>
                    <TableCell>{c.year}</TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

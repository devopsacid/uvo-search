import { Link, useParams } from 'react-router-dom'
import { BarChart3 } from 'lucide-react'
import { useSupplierPeriodSummary } from '@/api/queries/analytics'
import { DateRangePicker, useDateRange } from '@/components/ui/DateRangePicker'
import { KpiCard } from '@/components/ui/KpiCard'
import { MonthlySpendChart } from '@/components/charts/MonthlySpendChart'
import { DonutChart } from '@/components/charts/DonutChart'
import { HhiGauge } from '@/components/charts/HhiGauge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { EntityLink } from '@/components/entity/EntityLink'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

function ShareBar({ pct }: { pct: number }) {
  // pct is a 0–1 fraction.
  const display = Math.max(0, Math.min(pct, 1)) * 100
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary opacity-70"
          style={{ width: `${display}%` }}
        />
      </div>
      <span className="tabular-nums text-xs text-muted-foreground">{display.toFixed(1)} %</span>
    </div>
  )
}

export function SupplierAnalyticsPage() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''
  const { dateFrom, dateTo } = useDateRange()

  const { data, isLoading, isError } = useSupplierPeriodSummary(safeIco, dateFrom, dateTo)

  const searchLink = `/search?supplier_ico=${safeIco}&date_from=${dateFrom}&date_to=${dateTo}`

  if (isError) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">{sk.analytics.common.error}</p>
        <Link to={`/suppliers/${safeIco}`} className="mt-4 block text-sm text-primary hover:underline">
          ← {sk.analytics.supplier.breadcrumb}
        </Link>
      </div>
    )
  }

  const kpis = data?.kpis
  const deltas = kpis?.deltas

  const donutData = (data?.cpv_breakdown ?? []).slice(0, 10).map((c) => ({
    name: c.label_sk ?? c.cpv_code,
    value: c.total_value,
  }))

  return (
    <div className="space-y-6 print:space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link to={`/suppliers/${safeIco}`} className="hover:underline">
              {sk.analytics.supplier.breadcrumb}
            </Link>
            <span>/</span>
            <span>{sk.analytics.supplier.title}</span>
          </div>
          {isLoading ? (
            <Skeleton className="mt-1 h-7 w-64" />
          ) : (
            <h1 className="mt-1 text-xl font-semibold text-foreground">
              {data?.name ?? safeIco}
            </h1>
          )}
          <p className="mt-0.5 text-sm text-muted-foreground">{sk.suppliers.ico}: {safeIco}</p>
        </div>
        <DateRangePicker className="print:hidden" />
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
          ))
        ) : (
          <>
            <KpiCard
              label={sk.analytics.supplier.kpiRevenue}
              value={formatCurrency(kpis?.total_value ?? 0)}
              delta={deltas?.total_value_pct != null ? deltas.total_value_pct / 100 : null}
              subtext={
                kpis && kpis.value_coverage < 1
                  ? `${(kpis.value_coverage * 100).toFixed(0)} % ${sk.analytics.common.valueCoverage}`
                  : undefined
              }
            />
            <KpiCard
              label={sk.analytics.supplier.kpiContracts}
              value={formatNumber(kpis?.contract_count ?? 0)}
              delta={deltas?.contract_count_pct != null ? deltas.contract_count_pct / 100 : null}
            />
            <KpiCard
              label={sk.analytics.supplier.kpiAvg}
              value={formatCurrency(kpis?.avg_value ?? 0)}
              delta={deltas?.avg_value_pct != null ? deltas.avg_value_pct / 100 : null}
            />
            <KpiCard
              label={sk.analytics.supplier.kpiProcurers}
              value={formatNumber(kpis?.unique_counterparties ?? 0)}
              delta={
                deltas?.unique_counterparties_pct != null
                  ? deltas.unique_counterparties_pct / 100
                  : null
              }
            />
          </>
        )}
      </div>

      {/* Monthly spend chart */}
      <div className="rounded-lg border border-border bg-card p-4 print:break-inside-avoid">
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          {sk.analytics.common.sectionMonthly}
        </h2>
        {isLoading ? (
          <Skeleton className="h-60 w-full" />
        ) : (
          <MonthlySpendChart data={data?.monthly_spend ?? []} />
        )}
      </div>

      {/* Two-up: top procurers + CPV donut */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Top procurers */}
        <div className="rounded-lg border border-border bg-card print:break-inside-avoid">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">
              {sk.analytics.supplier.sectionProcurers}
            </h2>
          </div>
          <Table>
            <TableHeader>
              <tr>
                <TableHead>{sk.analytics.common.colName}</TableHead>
                <TableHead className="text-right">{sk.analytics.common.colContracts}</TableHead>
                <TableHead className="text-right">{sk.analytics.common.colValue}</TableHead>
                <TableHead>{sk.analytics.common.colShare}</TableHead>
              </tr>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 4 }).map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : (data?.top_counterparties ?? []).map((p, i) => (
                    <TableRow key={p.ico ?? i}>
                      <TableCell>
                        {p.ico ? (
                          <EntityLink ico={p.ico} name={p.name} type="procurer" />
                        ) : (
                          <span>{p.name}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatNumber(p.contract_count)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatCurrency(p.total_value)}
                      </TableCell>
                      <TableCell>
                        <ShareBar pct={p.share_pct} />
                      </TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
        </div>

        {/* CPV donut */}
        <div className="rounded-lg border border-border bg-card p-4 print:break-inside-avoid">
          <h2 className="mb-3 text-sm font-semibold text-foreground">
            {sk.analytics.common.sectionCpv}
          </h2>
          {isLoading ? (
            <Skeleton className="h-60 w-full" />
          ) : donutData.length ? (
            <DonutChart data={donutData} valueFormatter={formatCurrency} height={260} />
          ) : (
            <EmptyState title={sk.analytics.common.noData} />
          )}
        </div>
      </div>

      {/* Concentration card */}
      <div className="rounded-lg border border-border bg-card p-4 print:break-inside-avoid">
        <h2 className="mb-4 text-sm font-semibold text-foreground">
          {sk.analytics.common.sectionConcentration}
        </h2>
        {isLoading ? (
          <Skeleton className="h-32 w-40 mx-auto" />
        ) : data?.concentration ? (
          <HhiGauge
            hhi={data.concentration.hhi}
            top1SharePct={data.concentration.top1_share_pct}
            top3SharePct={data.concentration.top3_share_pct}
            className="max-w-xs mx-auto"
          />
        ) : null}
      </div>

      {/* Footer */}
      <div className="flex justify-center print:hidden">
        <Link
          to={searchLink}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <BarChart3 className="h-4 w-4" />
          {sk.analytics.common.showAllContracts}
        </Link>
      </div>
    </div>
  )
}

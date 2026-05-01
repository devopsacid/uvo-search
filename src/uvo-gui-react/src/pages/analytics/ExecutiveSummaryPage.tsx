import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useExecutiveSummary } from '@/api/queries/analytics'
import { DateRangePicker, useDateRange } from '@/components/ui/DateRangePicker'
import { KpiCard } from '@/components/ui/KpiCard'
import { AnomalyBanner } from '@/components/ui/AnomalyBanner'
import { PriorPeriodOverlayChart } from '@/components/charts/PriorPeriodOverlayChart'
import { DonutChart } from '@/components/charts/DonutChart'
import { HhiGauge } from '@/components/charts/HhiGauge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { EntityLink } from '@/components/entity/EntityLink'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

export function ExecutiveSummaryPage() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''
  const { dateFrom, dateTo } = useDateRange()
  const [searchParams, setSearchParams] = useSearchParams()

  const entityType =
    (searchParams.get('entity_type') as 'procurer' | 'supplier' | null) ?? 'procurer'

  function toggleEntityType() {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('entity_type', entityType === 'procurer' ? 'supplier' : 'procurer')
        return next
      },
      { replace: false },
    )
  }

  const { data, isLoading, isError } = useExecutiveSummary(safeIco, dateFrom, dateTo, entityType)

  if (isError) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">{sk.analytics.common.error}</p>
        <Link to="/analytics" className="mt-4 block text-sm text-primary hover:underline">
          ← {sk.analytics.executive.title}
        </Link>
      </div>
    )
  }

  const kpis = data?.kpis
  const deltas = kpis?.deltas
  const anomalies = data?.anomalies ?? []

  const donutData = (data?.cpv_breakdown ?? []).slice(0, 6).map((c) => ({
    name: c.label_sk ?? c.cpv_code,
    value: c.total_value,
  }))

  // The PeriodSummary shape only returns current monthly_spend; prior period data
  // is not yet in the contract. Pass empty array — overlay chart degrades gracefully.
  const priorData: import('@/api/types').MonthlySpendBucket[] = []

  return (
    <div className="space-y-6 print:space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link to="/analytics" className="hover:underline">
              {sk.analytics.executive.title}
            </Link>
          </div>
          {isLoading ? (
            <Skeleton className="mt-1 h-7 w-64" />
          ) : (
            <h1 className="mt-1 text-xl font-semibold text-foreground">
              {data?.name ?? safeIco}
            </h1>
          )}
          <p className="mt-0.5 text-sm text-muted-foreground">{sk.procurers.ico}: {safeIco}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 print:hidden">
          {/* Entity type toggle */}
          <div className="flex rounded-md border border-border overflow-hidden">
            <button
              type="button"
              onClick={() => entityType !== 'procurer' && toggleEntityType()}
              className={`px-3 py-1.5 text-sm transition-colors ${
                entityType === 'procurer'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent'
              }`}
            >
              {sk.analytics.executive.toggleProcurer}
            </button>
            <button
              type="button"
              onClick={() => entityType !== 'supplier' && toggleEntityType()}
              className={`px-3 py-1.5 text-sm transition-colors ${
                entityType === 'supplier'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent'
              }`}
            >
              {sk.analytics.executive.toggleSupplier}
            </button>
          </div>
          <DateRangePicker />
        </div>
      </div>

      {/* KPI strip — oversized for exec readability */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 print:break-inside-avoid">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-lg bg-muted" />
          ))
        ) : (
          <>
            <KpiCard
              label={
                entityType === 'procurer'
                  ? sk.analytics.procurer.kpiSpend
                  : sk.analytics.supplier.kpiRevenue
              }
              value={formatCurrency(kpis?.total_value ?? 0)}
              delta={deltas?.total_value_pct != null ? deltas.total_value_pct / 100 : null}
              large
              subtext={
                kpis && kpis.value_coverage < 1
                  ? `${(kpis.value_coverage * 100).toFixed(0)} % ${sk.analytics.common.valueCoverage}`
                  : undefined
              }
            />
            <KpiCard
              label={sk.analytics.procurer.kpiContracts}
              value={formatNumber(kpis?.contract_count ?? 0)}
              delta={deltas?.contract_count_pct != null ? deltas.contract_count_pct / 100 : null}
              large
            />
            <KpiCard
              label={sk.analytics.procurer.kpiAvg}
              value={formatCurrency(kpis?.avg_value ?? 0)}
              delta={deltas?.avg_value_pct != null ? deltas.avg_value_pct / 100 : null}
              large
            />
            <KpiCard
              label={
                entityType === 'procurer'
                  ? sk.analytics.procurer.kpiSuppliers
                  : sk.analytics.supplier.kpiProcurers
              }
              value={formatNumber(kpis?.unique_counterparties ?? 0)}
              delta={
                deltas?.unique_counterparties_pct != null
                  ? deltas.unique_counterparties_pct / 100
                  : null
              }
              large
            />
          </>
        )}
      </div>

      {/* Anomaly banners */}
      {!isLoading && anomalies.length > 0 && (
        <div className="print:break-inside-avoid">
          <h2 className="mb-2 text-sm font-semibold text-foreground">
            {sk.analytics.executive.anomaliesTitle}
          </h2>
          <AnomalyBanner anomalies={anomalies} max={3} />
        </div>
      )}

      {/* Trend chart with prior period overlay */}
      <div className="rounded-lg border border-border bg-card p-4 print:break-inside-avoid">
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          {sk.analytics.executive.sectionTrend}
        </h2>
        {isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : (data?.monthly_spend ?? []).length > 0 ? (
          <PriorPeriodOverlayChart
            current={data?.monthly_spend ?? []}
            prior={priorData}
            height={220}
          />
        ) : (
          <EmptyState title={sk.analytics.common.noData} />
        )}
      </div>

      {/* Two-up: top counterparties + CPV donut */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Top counterparties (top 5 only for exec view) */}
        <div className="rounded-lg border border-border bg-card print:break-inside-avoid">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">
              {sk.analytics.executive.sectionCounterparties}
            </h2>
          </div>
          <Table>
            <TableHeader>
              <tr>
                <TableHead>{sk.analytics.common.colName}</TableHead>
                <TableHead className="text-right">{sk.analytics.common.colContracts}</TableHead>
                <TableHead className="text-right">{sk.analytics.common.colValue}</TableHead>
              </tr>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 3 }).map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : (data?.top_counterparties ?? []).slice(0, 5).map((c, i) => (
                    <TableRow key={c.ico ?? i}>
                      <TableCell>
                        {c.ico ? (
                          <EntityLink
                            ico={c.ico}
                            name={c.name}
                            type={entityType === 'procurer' ? 'supplier' : 'procurer'}
                          />
                        ) : (
                          <span>{c.name}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatNumber(c.contract_count)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatCurrency(c.total_value)}
                      </TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
        </div>

        {/* CPV mix donut */}
        <div className="rounded-lg border border-border bg-card p-4 print:break-inside-avoid">
          <h2 className="mb-3 text-sm font-semibold text-foreground">
            {sk.analytics.common.sectionCpv}
          </h2>
          {isLoading ? (
            <Skeleton className="h-60 w-full" />
          ) : donutData.length ? (
            <DonutChart data={donutData} valueFormatter={formatCurrency} height={240} />
          ) : (
            <EmptyState title={sk.analytics.common.noData} />
          )}
        </div>
      </div>

      {/* Concentration block */}
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
    </div>
  )
}

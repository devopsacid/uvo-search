import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  useAnalyticsSummary,
  useAnalyticsTimeseries,
  useAnalyticsTop,
} from '@/api/queries/analytics'
import { useContractSearch } from '@/api/queries/contracts'
import type { AnalyticsGranularity, AnalyticsTopDimension, AnalyticsTopMetric } from '@/api/types'
import { ChartCard, ErrorPanel } from '@/components/analytics/ChartCard'
import { SimpleDataTable, TableLink } from '@/components/analytics/DataTableToggle'
import { KpiRow, type KpiItem } from '@/components/analytics/KpiRow'
import { TimeseriesChart } from '@/components/analytics/TimeseriesChart'
import { TopBarChart, type TopBarRow } from '@/components/analytics/TopBarChart'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Skeleton'
import { useAnalyticsFilters } from '@/hooks/useAnalyticsFilters'
import {
  autoGranularity,
  formatPeriodLabel,
  periodCaption,
  type AnalyticsFilters,
} from '@/lib/analyticsFilters'
import { firmaLink, zakazkyLink, zakazkyPeriodLink } from '@/lib/analyticsLinks'
import { csvFilename, downloadCsv, toCsv } from '@/lib/csv'
import {
  fillTemplate,
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
} from '@/lib/utils'
import sk from '@/i18n/sk'

const GRANULARITIES: AnalyticsGranularity[] = ['month', 'quarter', 'year']

export function PrehladPage() {
  const { filters, rangeProblem } = useAnalyticsFilters()
  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-sm text-muted-foreground">{sk.analytics.prehlad.intro}</p>
      <SummarySection filters={filters} disabled={rangeProblem !== null} />
      <TimeseriesSection filters={filters} />
      <div className="grid gap-5 xl:grid-cols-2">
        <TopSection filters={filters} dimension="procurer" />
        <TopSection filters={filters} dimension="supplier" />
      </div>
      <RecentSection filters={filters} />
    </div>
  )
}

// ── KPI row ───────────────────────────────────────────────────────────────────

function SummarySection({ filters, disabled }: { filters: AnalyticsFilters; disabled: boolean }) {
  const q = useAnalyticsSummary(filters)
  const href = zakazkyLink(filters)

  if (disabled) return null
  if (q.isError) return <ErrorPanel error={q.error} onRetry={() => void q.refetch()} />

  const s = q.data
  const k = sk.analytics.kpi
  const items: KpiItem[] = s
    ? [
        { key: 'value', label: k.totalValue, value: formatCurrency(s.current.total_value), deltaPct: s.deltas.total_value_pct, showDelta: true, href, title: k.includesEstimates },
        { key: 'count', label: k.contractCount, value: formatNumber(s.current.contract_count), deltaPct: s.deltas.contract_count_pct, showDelta: true, href },
        { key: 'avg', label: k.avgValue, value: formatCurrency(s.current.avg_value), deltaPct: s.deltas.avg_value_pct, showDelta: true, href, title: k.avgHint },
        { key: 'procurers', label: k.procurerCount, value: formatNumber(s.current.procurer_count), deltaPct: s.deltas.procurer_count_pct, showDelta: true, href },
        { key: 'suppliers', label: k.supplierCount, value: formatNumber(s.current.supplier_count), deltaPct: s.deltas.supplier_count_pct, showDelta: true, href },
      ]
    : []

  return (
    <section aria-label={sk.analytics.kpi.sectionLabel} className="space-y-2">
      <KpiRow items={items} isLoading={q.isLoading} />
      {s && (
        <p className="text-xs text-muted-foreground">
          {periodCaption(filters)} · {k.includesEstimates}.{' '}
          {s.previous
            ? fillTemplate(k.previousPeriod, {
                from: formatDate(s.previous.date_from),
                to: formatDate(s.previous.date_to),
              })
            : k.noPrevious}
        </p>
      )}
    </section>
  )
}

// ── Time series ───────────────────────────────────────────────────────────────

function TimeseriesSection({ filters }: { filters: AnalyticsFilters }) {
  const navigate = useNavigate()
  const [override, setOverride] = useState<AnalyticsGranularity | null>(null)
  const granularity = override ?? autoGranularity(filters)
  const q = useAnalyticsTimeseries(filters, { granularity })
  const points = q.data?.points ?? []
  const unit = sk.analytics.prehlad.granularityUnit[granularity]

  const peak = points.reduce<(typeof points)[number] | null>(
    (best, p) => (best === null || p.total_value > best.total_value ? p : best),
    null,
  )
  const title = sk.analytics.prehlad.timeseriesTitle
  const ariaLabel = peak
    ? fillTemplate(sk.analytics.aria.timeseries, {
        title,
        unit,
        from: formatDate(filters.date_from),
        to: formatDate(filters.date_to),
        peak: formatPeriodLabel(peak.period),
        value: formatCompactCurrency(peak.total_value),
      })
    : title

  function exportCsv() {
    downloadCsv(
      csvFilename('cas', filters.date_from, filters.date_to),
      toCsv(points, [
        { header: sk.analytics.csv.period, value: (p) => p.period },
        { header: sk.analytics.csv.totalValue, value: (p) => p.total_value },
        { header: sk.analytics.csv.contractCount, value: (p) => p.contract_count },
        { header: sk.analytics.csv.avgValue, value: (p) => p.avg_value },
      ]),
    )
  }

  return (
    <ChartCard
      title={title}
      caption={periodCaption(filters)}
      ariaLabel={ariaLabel}
      status={q}
      isEmpty={q.isSuccess && points.every((p) => p.contract_count === 0)}
      onExportCsv={exportCsv}
      actions={
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {sk.analytics.prehlad.granularity}
          <select
            value={granularity}
            onChange={(e) => setOverride(e.target.value as AnalyticsGranularity)}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {GRANULARITIES.map((g) => (
              <option key={g} value={g}>
                {sk.analytics.prehlad.granularities[g]}
              </option>
            ))}
          </select>
        </label>
      }
      chart={
        <TimeseriesChart
          points={points}
          onSelectPeriod={(period) => navigate(zakazkyPeriodLink(filters, period))}
        />
      }
      table={
        <SimpleDataTable
          caption={title}
          rows={points}
          rowKey={(p) => p.period}
          columns={[
            {
              header: sk.analytics.csv.period,
              cell: (p) => (
                <TableLink to={zakazkyPeriodLink(filters, p.period)}>{formatPeriodLabel(p.period)}</TableLink>
              ),
            },
            { header: sk.analytics.csv.totalValue, cell: (p) => formatCurrency(p.total_value), align: 'right' },
            { header: sk.analytics.csv.contractCount, cell: (p) => formatNumber(p.contract_count), align: 'right' },
            { header: sk.analytics.csv.avgValue, cell: (p) => formatCurrency(p.avg_value), align: 'right' },
          ]}
        />
      }
    />
  )
}

// ── Top procurers / suppliers ─────────────────────────────────────────────────

function TopSection({
  filters,
  dimension,
}: {
  filters: AnalyticsFilters
  dimension: Extract<AnalyticsTopDimension, 'procurer' | 'supplier'>
}) {
  const [metric, setMetric] = useState<AnalyticsTopMetric>('total_value')
  const q = useAnalyticsTop(filters, { dimension, metric, n: 10 })
  const data = q.data
  const isProcurer = dimension === 'procurer'
  const title = isProcurer ? sk.analytics.prehlad.topProcurers : sk.analytics.prehlad.topSuppliers
  const icoParam = isProcurer ? 'procurer_ico' : 'supplier_ico'

  const rows: TopBarRow[] = (data?.items ?? []).map((it) => ({
    key: it.key,
    label: it.label,
    amount: metric === 'total_value' ? it.total_value : it.contract_count,
    amountLabel: metric === 'total_value' ? formatCompactCurrency(it.total_value) : formatNumber(it.contract_count),
    sharePct: it.share_pct,
    shareLabel: formatPercent(it.share_pct),
    href: it.ico ? zakazkyLink(filters, { [icoParam]: it.ico }) : undefined,
    profileHref: it.ico ? firmaLink(it.ico) : undefined,
  }))
  if (data && data.other.contract_count > 0) {
    const o = data.other
    rows.push({
      key: 'other',
      label: sk.analytics.otherEntities,
      amount: metric === 'total_value' ? o.total_value : o.contract_count,
      amountLabel: metric === 'total_value' ? formatCompactCurrency(o.total_value) : formatNumber(o.contract_count),
      sharePct: o.share_pct,
      shareLabel: formatPercent(o.share_pct),
      muted: true,
    })
  }

  const first = data?.items[0]
  const ariaLabel = first
    ? fillTemplate(sk.analytics.aria.top, {
        title,
        first: first.label,
        value: formatCompactCurrency(first.total_value),
        share: formatPercent(first.share_pct),
      })
    : title

  function exportCsv() {
    downloadCsv(
      csvFilename(isProcurer ? 'top-obstaravatelia' : 'top-dodavatelia', filters.date_from, filters.date_to),
      toCsv(data?.items ?? [], [
        { header: sk.analytics.csv.name, value: (r) => r.label },
        { header: sk.common.ico, value: (r) => r.ico },
        { header: sk.analytics.csv.totalValue, value: (r) => r.total_value },
        { header: sk.analytics.csv.contractCount, value: (r) => r.contract_count },
        { header: sk.analytics.csv.sharePct, value: (r) => r.share_pct },
      ]),
    )
  }

  return (
    <ChartCard
      title={title}
      caption={periodCaption(filters)}
      ariaLabel={ariaLabel}
      status={q}
      isEmpty={q.isSuccess && (data?.items.length ?? 0) === 0}
      onExportCsv={exportCsv}
      asImage={false}
      skeletonClassName="h-72"
      actions={
        <div role="group" aria-label={sk.analytics.prehlad.metric} className="flex overflow-hidden rounded-md border border-border text-xs">
          {(['total_value', 'contract_count'] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={metric === m}
              onClick={() => setMetric(m)}
              className={`px-2.5 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                metric === m ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
              }`}
            >
              {m === 'total_value' ? sk.analytics.prehlad.metricValue : sk.analytics.prehlad.metricCount}
            </button>
          ))}
        </div>
      }
      chart={<TopBarChart rows={rows} ariaLabel={ariaLabel} />}
      table={
        <SimpleDataTable
          caption={title}
          rows={data?.items ?? []}
          rowKey={(r) => r.key}
          columns={[
            {
              header: sk.analytics.csv.name,
              cell: (r) => (r.ico ? <TableLink to={firmaLink(r.ico)}>{r.label}</TableLink> : r.label),
            },
            { header: sk.analytics.csv.totalValue, cell: (r) => formatCurrency(r.total_value), align: 'right' },
            { header: sk.analytics.csv.contractCount, cell: (r) => formatNumber(r.contract_count), align: 'right' },
            { header: sk.analytics.csv.sharePct, cell: (r) => formatPercent(r.share_pct), align: 'right' },
            {
              header: sk.analytics.charts.showContracts,
              cell: (r) =>
                r.ico ? (
                  <TableLink to={zakazkyLink(filters, { [icoParam]: r.ico })}>{sk.analytics.charts.showContracts}</TableLink>
                ) : null,
            },
          ]}
        />
      }
    />
  )
}

// ── Recent contracts ──────────────────────────────────────────────────────────

function RecentSection({ filters }: { filters: AnalyticsFilters }) {
  const q = useContractSearch({
    date_from: filters.date_from,
    date_to: filters.date_to,
    cpv: filters.cpv,
    source: filters.source,
    procurer_ico: filters.procurer_ico,
    supplier_ico: filters.supplier_ico,
    page_size: 8,
  })
  const rows = q.data?.data ?? []

  return (
    <section className="rounded-lg border border-border bg-card p-4" aria-labelledby="recent-title">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="recent-title" className="text-sm font-semibold text-foreground">
          {sk.analytics.prehlad.recentTitle}
        </h3>
        <Link to={zakazkyLink(filters)} className="text-xs text-primary hover:underline">
          {sk.analytics.prehlad.allContracts}
        </Link>
      </div>
      {q.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : q.isError ? (
        <ErrorPanel error={q.error} onRetry={() => void q.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title={sk.analytics.charts.emptyTitle} description={sk.analytics.charts.emptyHint} className="py-8" />
      ) : (
        <SimpleDataTable
          caption={sk.analytics.prehlad.recentTitle}
          rows={rows}
          rowKey={(c) => c.id}
          columns={[
            {
              header: sk.search.colTitle,
              cell: (c) => (
                <TableLink to={zakazkyLink(filters, { selected: c.id })}>
                  <span className="line-clamp-2">{c.title}</span>
                </TableLink>
              ),
            },
            { header: sk.search.colProcurer, cell: (c) => c.procurer_name || '—' },
            { header: sk.search.colSupplier, cell: (c) => c.supplier_name || '—' },
            { header: sk.search.colValue, cell: (c) => formatCurrency(c.value), align: 'right' },
            { header: sk.search.colYear, cell: (c) => c.year || '—' },
          ]}
        />
      )}
      <p className="mt-3 text-xs text-muted-foreground">{sk.analytics.prehlad.recentHint}</p>
    </section>
  )
}

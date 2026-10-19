import { useMemo, useState } from 'react'
import { useAnalyticsCpv, useAnalyticsTimeseries } from '@/api/queries/analytics'
import type { CpvBucket } from '@/api/types'
import { ChartCard, ErrorPanel, InvalidRangeNotice } from '@/components/analytics/ChartCard'
import { SimpleDataTable, TableLink } from '@/components/analytics/DataTableToggle'
import { StackedPeriodChart } from '@/components/analytics/StackedPeriodChart'
import { TopBarChart, type TopBarRow } from '@/components/analytics/TopBarChart'
import { useAnalyticsFilters } from '@/hooks/useAnalyticsFilters'
import { autoGranularity, formatPeriodLabel, periodCaption, type AnalyticsFilters } from '@/lib/analyticsFilters'
import { analyticsLink, contractsLink } from '@/lib/analyticsLinks'
import { pivotSeries } from '@/lib/analyticsSeries'
import { csvFilename, downloadCsv, toCsv } from '@/lib/csv'
import { cn, fillTemplate, formatCompactCurrency, formatCurrency, formatNumber, formatPercent } from '@/lib/utils'
import sk from '@/i18n/sk'

const TOP_N = 10

export function CpvPage() {
  const { filters, rangeProblem } = useAnalyticsFilters()
  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-sm text-muted-foreground">{sk.analytics.cpv.intro}</p>
      {rangeProblem ? <InvalidRangeNotice problem={rangeProblem} /> : <Body filters={filters} />}
    </div>
  )
}

function Body({ filters }: { filters: AnalyticsFilters }) {
  const level = filters.cpv && filters.cpv.length >= 2 ? 'group' : 'division'
  const q = useAnalyticsCpv(filters, level)
  if (q.isError) return <ErrorPanel error={q.error} onRetry={() => void q.refetch()} />
  return (
    <>
      <SharesCard filters={filters} level={level} q={q} />
      <TrendCard filters={filters} />
      <DivisionsTable filters={filters} level={level} q={q} />
    </>
  )
}

type CpvQuery = ReturnType<typeof useAnalyticsCpv>

/** Where a bucket leads: divisions narrow the dashboard to that sector, groups open the contract list. */
function bucketHref(filters: AnalyticsFilters, level: 'division' | 'group', b: CpvBucket): string {
  return level === 'division'
    ? analyticsLink('cpv', { ...filters, cpv: b.prefix })
    : contractsLink(filters, { cpv: b.prefix })
}

function bucketLabel(b: CpvBucket): string {
  return b.label_sk && b.label_sk !== b.cpv_code ? b.label_sk : b.cpv_code
}

function SharesCard({ filters, level, q }: { filters: AnalyticsFilters; level: 'division' | 'group'; q: CpvQuery }) {
  const items = useMemo(() => q.data?.items ?? [], [q.data])
  const top = items.slice(0, TOP_N)
  const rest = items.slice(TOP_N)
  const otherValue = rest.reduce((s, b) => s + b.total_value, 0)
  const otherShare = rest.reduce((s, b) => s + b.share_pct, 0)

  const rows: TopBarRow[] = top.map((b) => ({
    key: b.cpv_code,
    label: `${b.prefix} · ${bucketLabel(b)}`,
    amount: b.total_value,
    amountLabel: formatCompactCurrency(b.total_value),
    sharePct: b.share_pct,
    shareLabel: formatPercent(b.share_pct),
    href: bucketHref(filters, level, b),
  }))
  if (rest.length > 0) {
    rows.push({
      key: 'other',
      label: sk.analytics.otherSectors,
      amount: otherValue,
      amountLabel: formatCompactCurrency(otherValue),
      sharePct: otherShare,
      shareLabel: formatPercent(otherShare),
      muted: true,
    })
  }

  const title = level === 'group' ? sk.analytics.cpv.sharesTitleGroup : sk.analytics.cpv.sharesTitle
  const ariaLabel = top[0]
    ? fillTemplate(sk.analytics.aria.top, {
        title,
        first: bucketLabel(top[0]),
        value: formatCompactCurrency(top[0].total_value),
        share: formatPercent(top[0].share_pct),
      })
    : title

  return (
    <ChartCard
      title={title}
      caption={`${periodCaption(filters)}${filters.cpv ? ` · CPV ${filters.cpv}` : ''}`}
      ariaLabel={ariaLabel}
      status={q}
      isEmpty={q.isSuccess && items.length === 0}
      asImage={false}
      skeletonClassName="h-72"
      onExportCsv={() => exportBuckets(filters, items, `cpv-${level}`)}
      chart={
        <div className="space-y-2">
          <TopBarChart rows={rows} ariaLabel={ariaLabel} />
          <p className="pt-1 text-xs text-muted-foreground">
            {level === 'division' ? sk.analytics.cpv.drillHintDivision : sk.analytics.cpv.drillHintGroup}
          </p>
        </div>
      }
    />
  )
}

function exportBuckets(filters: AnalyticsFilters, items: CpvBucket[], view: string) {
  downloadCsv(
    csvFilename(view, filters.date_from, filters.date_to),
    toCsv(items, [
      { header: sk.analytics.csv.code, value: (b) => b.cpv_code },
      { header: sk.analytics.csv.name, value: (b) => bucketLabel(b) },
      { header: sk.analytics.csv.totalValue, value: (b) => b.total_value },
      { header: sk.analytics.csv.contractCount, value: (b) => b.contract_count },
      { header: sk.analytics.csv.sharePct, value: (b) => b.share_pct },
    ]),
  )
}

function TrendCard({ filters }: { filters: AnalyticsFilters }) {
  const granularity = autoGranularity(filters) === 'month' ? 'quarter' : 'year'
  const q = useAnalyticsTimeseries(filters, { granularity, split_by: 'cpv_division', top: 5 })
  const series = q.data?.series ?? []
  const title = sk.analytics.cpv.trendTitle

  const ariaLabel = series.length
    ? fillTemplate(sk.analytics.aria.stacked, {
        title,
        from: formatPeriodLabel(series[0].points[0]?.period ?? ''),
        to: formatPeriodLabel(series[0].points[series[0].points.length - 1]?.period ?? ''),
        series: series.map((s) => s.label).join(', '),
      })
    : title

  const rows = pivotSeries(series)

  return (
    <ChartCard
      title={title}
      caption={periodCaption(filters)}
      ariaLabel={ariaLabel}
      status={q}
      isEmpty={q.isSuccess && series.length === 0}
      onExportCsv={() =>
        downloadCsv(
          csvFilename('cpv-trend', filters.date_from, filters.date_to),
          toCsv(rows, [
            { header: sk.analytics.csv.period, value: (r) => String(r.period) },
            ...series.map((s) => ({ header: s.label, value: (r: Record<string, string | number>) => r[s.key] ?? 0 })),
          ]),
        )
      }
      chart={<StackedPeriodChart series={series} />}
      table={
        <SimpleDataTable
          caption={title}
          rows={rows}
          rowKey={(r) => String(r.period)}
          columns={[
            { header: sk.analytics.csv.period, cell: (r) => String(r.label) },
            ...series.map((s) => ({
              header: s.label,
              cell: (r: Record<string, string | number>) => formatCurrency(Number(r[s.key] ?? 0)),
              align: 'right' as const,
            })),
          ]}
        />
      }
    />
  )
}

type SortKey = 'code' | 'name' | 'value' | 'count' | 'share'

function DivisionsTable({ filters, level, q }: { filters: AnalyticsFilters; level: 'division' | 'group'; q: CpvQuery }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'value', dir: 'desc' })
  const items = useMemo(() => q.data?.items ?? [], [q.data])
  const t = sk.analytics.cpv

  const sorted = useMemo(() => {
    const factor = sort.dir === 'asc' ? 1 : -1
    const get: Record<SortKey, (b: CpvBucket) => string | number> = {
      code: (b) => b.cpv_code,
      name: (b) => bucketLabel(b),
      value: (b) => b.total_value,
      count: (b) => b.contract_count,
      share: (b) => b.share_pct,
    }
    return [...items].sort((a, b) => {
      const x = get[sort.key](a)
      const y = get[sort.key](b)
      return (typeof x === 'string' && typeof y === 'string' ? x.localeCompare(y, 'sk') : Number(x) - Number(y)) * factor
    })
  }, [items, sort])

  function toggle(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'code' || key === 'name' ? 'asc' : 'desc' }))
  }

  const columns: { key: SortKey; header: string; right?: boolean }[] = [
    { key: 'code', header: t.colCode },
    { key: 'name', header: t.colName },
    { key: 'value', header: sk.analytics.csv.totalValue, right: true },
    { key: 'count', header: sk.analytics.csv.contractCount, right: true },
    { key: 'share', header: sk.analytics.csv.sharePct, right: true },
  ]

  if (q.isLoading || items.length === 0) return null

  return (
    <section className="rounded-lg border border-border bg-card p-4" aria-labelledby="cpv-table-title">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 id="cpv-table-title" className="text-sm font-semibold text-foreground">
          {t.tableTitle}
        </h3>
        <button
          type="button"
          onClick={() => exportBuckets(filters, sorted, `cpv-${level}-tabulka`)}
          className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {sk.analytics.charts.exportCsv}
        </button>
      </div>
      <div className="w-full overflow-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{t.tableTitle}</caption>
          <thead className="border-b border-border">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  className={cn('h-10 px-3 text-xs font-medium text-muted-foreground', c.right ? 'text-right' : 'text-left')}
                >
                  <button
                    type="button"
                    onClick={() => toggle(c.key)}
                    className="inline-flex items-center gap-1 rounded hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {c.header}
                    <span aria-hidden="true">{sort.key === c.key ? (sort.dir === 'asc' ? '↑' : '↓') : ''}</span>
                  </button>
                </th>
              ))}
              <th scope="col" className="h-10 px-3 text-left text-xs font-medium text-muted-foreground">
                {sk.analytics.charts.showContracts}
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((b) => (
              <tr key={b.cpv_code} className="border-b border-border">
                <td className="px-3 py-2.5 tabular-nums">
                  <TableLink to={bucketHref(filters, level, b)}>{b.prefix}</TableLink>
                </td>
                <td className="px-3 py-2.5">{bucketLabel(b)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(b.total_value)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(b.contract_count)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(b.share_pct)}</td>
                <td className="px-3 py-2.5">
                  <TableLink to={contractsLink(filters, { cpv: b.prefix })}>{sk.analytics.charts.showContracts}</TableLink>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

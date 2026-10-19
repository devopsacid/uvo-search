import { useSearchParams } from 'react-router-dom'
import { useAnalyticsConcentration, useConcentrationByYear } from '@/api/queries/analytics'
import type { AnalyticsConcentrationDimension, ConcentrationEntry } from '@/api/types'
import { ChartCard, ErrorPanel, InvalidRangeNotice } from '@/components/analytics/ChartCard'
import { SimpleDataTable, TableLink } from '@/components/analytics/DataTableToggle'
import { HhiBadge } from '@/components/analytics/HhiBadge'
import { HhiTrendChart } from '@/components/analytics/HhiTrendChart'
import { KpiRow, type KpiItem } from '@/components/analytics/KpiRow'
import { ShareStackBar, type ShareSegment } from '@/components/analytics/ShareStackBar'
import { useAnalyticsFilters } from '@/hooks/useAnalyticsFilters'
import { periodCaption, type AnalyticsFilters } from '@/lib/analyticsFilters'
import { companyLink, contractsLink } from '@/lib/analyticsLinks'
import { csvFilename, downloadCsv, toCsv } from '@/lib/csv'
import { fillTemplate, formatCompactCurrency, formatCurrency, formatNumber, formatPercent } from '@/lib/utils'
import sk from '@/i18n/sk'

const DIMENSIONS: AnalyticsConcentrationDimension[] = ['supplier', 'procurer']

export function ConcentrationPage() {
  const { filters, rangeProblem } = useAnalyticsFilters()
  const [params, setParams] = useSearchParams()
  const dimension: AnalyticsConcentrationDimension = params.get('dimension') === 'procurer' ? 'procurer' : 'supplier'
  const t = sk.analytics.concentration

  function selectDimension(d: AnalyticsConcentrationDimension) {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (d === 'supplier') next.delete('dimension')
      else next.set('dimension', d)
      return next
    })
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">{t.intro}</p>
        <div role="group" aria-label={t.dimensionLabel} className="flex overflow-hidden rounded-md border border-border text-sm">
          {DIMENSIONS.map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={dimension === d}
              onClick={() => selectDimension(d)}
              className={`px-3 py-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                dimension === d ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
              }`}
            >
              {t.dimensions[d]}
            </button>
          ))}
        </div>
      </div>
      {rangeProblem ? <InvalidRangeNotice problem={rangeProblem} /> : <Body filters={filters} dimension={dimension} />}
      <p className="text-xs text-muted-foreground">{t.hint}</p>
    </div>
  )
}

function Body({ filters, dimension }: { filters: AnalyticsFilters; dimension: AnalyticsConcentrationDimension }) {
  const t = sk.analytics.concentration
  const q = useAnalyticsConcentration(filters, dimension)
  const d = q.data

  if (q.isError) return <ErrorPanel error={q.error} onRetry={() => void q.refetch()} />

  const empty = q.isSuccess && (d?.entity_count ?? 0) === 0
  const href = contractsLink(filters)
  const items: KpiItem[] = d
    ? [
        { key: 'hhi', label: t.hhi, value: formatNumber(Math.round(d.hhi)), href, extra: <HhiBadge band={d.hhi_band} />, title: t.hhiHint },
        { key: 'cr4', label: t.cr4, value: formatPercent(d.cr4_pct), href },
        { key: 'cr10', label: t.cr10, value: formatPercent(d.cr10_pct), href },
        { key: 'count', label: t.entityCount, value: formatNumber(d.entity_count), href },
      ]
    : []

  return (
    <>
      {!empty && <KpiRow items={items} isLoading={q.isLoading} skeletonCount={4} columnsClassName="grid-cols-2 lg:grid-cols-4" />}
      <SharesCard filters={filters} dimension={dimension} data={d} status={q} empty={empty} />
      <TrendCard filters={filters} dimension={dimension} />
    </>
  )
}

function SharesCard({
  filters,
  dimension,
  data,
  status,
  empty,
}: {
  filters: AnalyticsFilters
  dimension: AnalyticsConcentrationDimension
  data: ReturnType<typeof useAnalyticsConcentration>['data']
  status: ReturnType<typeof useAnalyticsConcentration>
  empty: boolean
}) {
  const t = sk.analytics.concentration
  const top = data?.top ?? []
  const icoParam = dimension === 'supplier' ? 'supplier_ico' : 'procurer_ico'
  const listedShare = top.reduce((sum, e) => sum + e.share_pct, 0)
  const otherShare = Math.max(0, 100 - listedShare)

  const segments: ShareSegment[] = top.map((e) => ({
    key: e.ico,
    label: e.name,
    sharePct: e.share_pct,
    shareLabel: formatPercent(e.share_pct),
  }))
  if (otherShare >= 0.05) {
    segments.push({
      key: 'other',
      label: sk.analytics.otherEntities,
      sharePct: otherShare,
      shareLabel: formatPercent(otherShare),
    })
  }

  const title = t.sharesTitle[dimension]
  const ariaLabel = top[0]
    ? fillTemplate(sk.analytics.aria.shares, {
        title,
        first: top[0].name,
        share: formatPercent(top[0].share_pct),
        count: top.length,
      })
    : title

  function exportCsv() {
    downloadCsv(
      csvFilename(`concentration-${dimension}`, filters.date_from, filters.date_to),
      toCsv(top, [
        { header: sk.analytics.csv.name, value: (e: ConcentrationEntry) => e.name },
        { header: sk.common.ico, value: (e) => e.ico },
        { header: sk.analytics.csv.totalValue, value: (e) => e.total_value },
        { header: sk.analytics.csv.sharePct, value: (e) => e.share_pct },
        { header: sk.analytics.csv.cumulativePct, value: (e) => e.cumulative_pct },
      ]),
    )
  }

  return (
    <ChartCard
      title={title}
      caption={periodCaption(filters)}
      ariaLabel={ariaLabel}
      status={status}
      isEmpty={empty}
      onExportCsv={exportCsv}
      asImage={false}
      chart={
        <div className="space-y-5">
          <div role="img" aria-label={ariaLabel}>
            <ShareStackBar segments={segments} />
          </div>
          <SimpleDataTable
            caption={title}
            rows={top}
            rowKey={(e) => e.ico}
            columns={[
              { header: sk.analytics.csv.name, cell: (e) => <TableLink to={companyLink(e.ico)}>{e.name}</TableLink> },
              { header: sk.analytics.csv.totalValue, cell: (e) => formatCurrency(e.total_value), align: 'right' },
              { header: sk.analytics.csv.sharePct, cell: (e) => formatPercent(e.share_pct), align: 'right' },
              { header: sk.analytics.csv.cumulativePct, cell: (e) => formatPercent(e.cumulative_pct), align: 'right' },
              {
                header: sk.analytics.charts.showContracts,
                cell: (e) => (
                  <TableLink to={contractsLink(filters, { [icoParam]: e.ico })}>{sk.analytics.charts.showContracts}</TableLink>
                ),
              },
            ]}
          />
          {data && (
            <p className="text-xs text-muted-foreground">
              {fillTemplate(t.totalNote, { value: formatCompactCurrency(data.total_value), count: formatNumber(data.entity_count) })}
            </p>
          )}
        </div>
      }
    />
  )
}

function TrendCard({ filters, dimension }: { filters: AnalyticsFilters; dimension: AnalyticsConcentrationDimension }) {
  const t = sk.analytics.concentration
  const { slices, results } = useConcentrationByYear(filters, dimension)

  const points = slices.map((s, i) => {
    const r = results[i]?.data
    return { year: s.year, hhi: r && r.entity_count > 0 ? Math.round(r.hhi) : null, band: r?.hhi_band ?? null }
  })
  const allLoading = results.length > 0 && results.every((r) => r.isLoading)
  const allError = results.length > 0 && results.every((r) => r.isError)
  const anyFetching = results.some((r) => r.isFetching)
  const settled = results.length > 0 && results.every((r) => r.isSuccess)
  const isEmpty = settled && points.every((p) => p.hhi === null)
  const firstError = results.find((r) => r.isError)

  const latest = [...points].reverse().find((p) => p.hhi !== null)
  const ariaLabel = latest
    ? fillTemplate(sk.analytics.aria.hhiTrend, {
        title: t.trendTitle,
        from: points[0].year,
        to: points[points.length - 1].year,
        last: latest.year,
        value: formatNumber(latest.hhi ?? 0),
      })
    : t.trendTitle

  function exportCsv() {
    downloadCsv(
      csvFilename(`hhi-${dimension}`, filters.date_from, filters.date_to),
      toCsv(points, [
        { header: sk.common.year, value: (p) => p.year },
        { header: t.hhiShort, value: (p) => p.hhi },
      ]),
    )
  }

  return (
    <ChartCard
      title={t.trendTitle}
      caption={periodCaption(filters)}
      ariaLabel={ariaLabel}
      status={{
        isLoading: allLoading,
        isError: allError,
        error: firstError?.error,
        isFetching: anyFetching,
        refetch: () => results.forEach((r) => void r.refetch()),
      }}
      isEmpty={isEmpty}
      onExportCsv={exportCsv}
      chart={<HhiTrendChart points={points} />}
      table={
        <SimpleDataTable
          caption={t.trendTitle}
          rows={points}
          rowKey={(p) => String(p.year)}
          columns={[
            { header: sk.common.year, cell: (p) => p.year },
            { header: t.hhiShort, cell: (p) => (p.hhi === null ? '—' : formatNumber(p.hhi)), align: 'right' },
            { header: t.bandColumn, cell: (p) => (p.band && p.hhi !== null ? t.bands[p.band] : '—') },
          ]}
        />
      }
    />
  )
}

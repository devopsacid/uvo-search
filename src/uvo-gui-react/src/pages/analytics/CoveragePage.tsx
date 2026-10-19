import { useAnalyticsCoverage } from '@/api/queries/analytics'
import type { AnalyticsCoverage, AnalyticsSource, TimeseriesSeries } from '@/api/types'
import { ChartCard, ErrorPanel } from '@/components/analytics/ChartCard'
import { SimpleDataTable } from '@/components/analytics/DataTableToggle'
import { KpiRow } from '@/components/analytics/KpiRow'
import { SourceCards } from '@/components/analytics/SourceCards'
import { StackedPeriodChart } from '@/components/analytics/StackedPeriodChart'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatPeriodLabel } from '@/lib/analyticsFilters'
import { csvFilename, downloadCsv, toCsv } from '@/lib/csv'
import { fillTemplate, formatNumber, formatPercent } from '@/lib/utils'
import sk from '@/i18n/sk'

const SOURCE_ORDER: AnalyticsSource[] = ['vestnik', 'crz', 'ted', 'itms', 'uvo']

function monthlySeries(cov: AnalyticsCoverage): TimeseriesSeries[] {
  return SOURCE_ORDER.filter((s) => cov.monthly.some((m) => m[s] > 0)).map((source) => ({
    key: source,
    label: sk.analytics.filters.sources[source],
    points: cov.monthly.map((m) => ({
      period: m.period,
      contract_count: m[source],
      total_value: 0,
      avg_value: 0,
    })),
  }))
}

export function CoveragePage() {
  const q = useAnalyticsCoverage()
  const cov = q.data
  const t = sk.analytics.coverage
  const first = cov?.monthly[0]?.period ?? 'od'
  const last = cov?.monthly[cov.monthly.length - 1]?.period ?? 'do'

  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-sm text-muted-foreground">{t.intro}</p>

      {q.isError ? (
        <ErrorPanel error={q.error} onRetry={() => void q.refetch()} />
      ) : q.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : cov ? (
        <SourceCards sources={cov.sources} />
      ) : null}

      <MonthlyCard q={q} cov={cov} from={first} to={last} />
      <QualityCard q={q} cov={cov} from={first} to={last} />

      {cov && (
        <section aria-label={t.canonicalTitle} className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground">{t.canonicalTitle}</h3>
          <KpiRow
            columnsClassName="grid-cols-2"
            items={[
              { key: 'cn', label: t.canonicalNotices, value: formatNumber(cov.canonical.notices_with_canonical_id) },
              { key: 'cg', label: t.canonicalGroups, value: formatNumber(cov.canonical.match_groups) },
            ]}
          />
          <p className="text-xs text-muted-foreground">{t.canonicalHint}</p>
        </section>
      )}
    </div>
  )
}

type CoverageQuery = ReturnType<typeof useAnalyticsCoverage>

function MonthlyCard({ q, cov, from, to }: { q: CoverageQuery; cov?: AnalyticsCoverage; from: string; to: string }) {
  const t = sk.analytics.coverage
  const series = cov ? monthlySeries(cov) : []
  const months = cov?.monthly ?? []
  const ariaLabel = months.length
    ? fillTemplate(sk.analytics.aria.stacked, {
        title: t.monthlyTitle,
        from: formatPeriodLabel(months[0].period),
        to: formatPeriodLabel(months[months.length - 1].period),
        series: series.map((s) => s.label).join(', '),
      })
    : t.monthlyTitle

  return (
    <ChartCard
      title={t.monthlyTitle}
      caption={t.monthlyCaption}
      ariaLabel={ariaLabel}
      status={q}
      hideEmptyAction
      isEmpty={q.isSuccess && series.length === 0}
      onExportCsv={() =>
        downloadCsv(
          csvFilename('coverage-monthly', from, to),
          toCsv(months, [
            { header: sk.analytics.csv.period, value: (m) => m.period },
            ...SOURCE_ORDER.map((s) => ({ header: sk.analytics.filters.sources[s], value: (m: (typeof months)[number]) => m[s] })),
          ]),
        )
      }
      chart={<StackedPeriodChart series={series} metric="contract_count" />}
      table={
        <SimpleDataTable
          caption={t.monthlyTitle}
          rows={months}
          rowKey={(m) => m.period}
          columns={[
            { header: sk.analytics.csv.period, cell: (m) => formatPeriodLabel(m.period) },
            ...SOURCE_ORDER.map((s) => ({
              header: sk.analytics.filters.sources[s],
              cell: (m: (typeof months)[number]) => formatNumber(m[s]),
              align: 'right' as const,
            })),
          ]}
        />
      }
    />
  )
}

function QualityCard({ q, cov, from, to }: { q: CoverageQuery; cov?: AnalyticsCoverage; from: string; to: string }) {
  const t = sk.analytics.coverage
  const sources = cov?.sources ?? []
  return (
    <ChartCard
      title={t.qualityTitle}
      caption={t.qualityCaption}
      ariaLabel={t.qualityTitle}
      status={q}
      hideEmptyAction
      asImage={false}
      skeletonClassName="h-40"
      isEmpty={q.isSuccess && sources.length === 0}
      onExportCsv={() =>
        downloadCsv(
          csvFilename('coverage-quality', from, to),
          toCsv(sources, [
            { header: t.colSource, value: (s) => sk.analytics.filters.sources[s.source] },
            { header: t.colWithValue, value: (s) => s.quality.with_value_pct },
            { header: t.colWithCpv, value: (s) => s.quality.with_cpv_pct },
            { header: t.colWithSupplier, value: (s) => s.quality.with_supplier_ico_pct },
            { header: t.colWithProcurer, value: (s) => s.quality.with_procurer_ico_pct },
          ]),
        )
      }
      chart={
        <SimpleDataTable
          caption={t.qualityTitle}
          rows={sources}
          rowKey={(s) => s.source}
          columns={[
            { header: t.colSource, cell: (s) => sk.analytics.filters.sources[s.source] },
            { header: t.colWithValue, cell: (s) => formatPercent(s.quality.with_value_pct), align: 'right' },
            { header: t.colWithCpv, cell: (s) => formatPercent(s.quality.with_cpv_pct), align: 'right' },
            { header: t.colWithSupplier, cell: (s) => formatPercent(s.quality.with_supplier_ico_pct), align: 'right' },
            { header: t.colWithProcurer, cell: (s) => formatPercent(s.quality.with_procurer_ico_pct), align: 'right' },
          ]}
        />
      }
    />
  )
}

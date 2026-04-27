import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import { useIngestionDashboard } from '@/api/queries/ingestion'
import { IngestionLogPanel } from '@/components/ingestion/IngestionLogPanel'
import { WorkerStatusTable } from '@/components/ingestion/WorkerStatusTable'
import type { IngestionSource, IngestionSourceStatus } from '@/api/types'
import { Skeleton, SkeletonCard } from '@/components/ui/Skeleton'
import { cn, formatBytes, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

// ── Constants ─────────────────────────────────────────────────────────────────

const SOURCE_NAMES = ['vestnik', 'crz', 'ted', 'uvo', 'itms'] as const
type SourceName = (typeof SOURCE_NAMES)[number]

const SOURCE_COLORS: Record<SourceName, string> = {
  vestnik: '#4f86c6',
  crz: '#62b58f',
  ted: '#e8a838',
  uvo: '#c96868',
  itms: '#9b77b8',
}

// ── Formatters ────────────────────────────────────────────────────────────────

function formatSlovakDateTime(isoString: string): string {
  return new Intl.DateTimeFormat('sk-SK', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(isoString))
}

function formatShortDate(isoDate: string): string {
  const [, month, day] = isoDate.split('-')
  return `${day}.${month}.`
}

function formatAge(seconds: number | null): string {
  if (seconds === null) return sk.ingestion.ageNever
  const mins = Math.floor(seconds / 60)
  const hours = Math.floor(mins / 60)
  const days = Math.floor(hours / 24)
  if (days >= 2) return `pred ${days} dňami`
  if (days === 1) return `pred 1 dňom`
  if (hours >= 1) {
    const remMins = mins % 60
    return remMins > 0 ? `pred ${hours} h ${remMins} min` : `pred ${hours} h`
  }
  if (mins >= 1) return `pred ${mins} min`
  return 'práve teraz'
}

function formatPercent(rate: number): string {
  return new Intl.NumberFormat('sk-SK', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(rate * 100)
}

// ── Status helpers ────────────────────────────────────────────────────────────

function statusLabel(status: IngestionSourceStatus): string {
  switch (status) {
    case 'healthy': return sk.ingestion.statusHealthy
    case 'warning': return sk.ingestion.statusWarning
    case 'stale':   return sk.ingestion.statusStale
    case 'unknown': return sk.ingestion.statusUnknown
  }
}

function statusBadgeClass(status: IngestionSourceStatus): string {
  switch (status) {
    case 'healthy': return 'bg-green-100 text-green-800'
    case 'warning': return 'bg-yellow-100 text-yellow-800'
    case 'stale':   return 'bg-red-100 text-red-800'
    case 'unknown': return 'bg-gray-100 text-gray-600'
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-lg border border-border bg-card p-4', className)}>
      {children}
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-3 text-sm font-semibold text-foreground">{children}</h2>
}

interface KpiTileProps {
  label: string
  value: React.ReactNode
  className?: string
}

function KpiTile({ label, value, className }: KpiTileProps) {
  return (
    <div className={cn('rounded-lg border border-border bg-card p-4', className)}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  )
}

type SortKey = 'status' | 'age_seconds'
type SortDir = 'asc' | 'desc'

const STATUS_ORDER: Record<IngestionSourceStatus, number> = {
  stale: 0,
  warning: 1,
  unknown: 2,
  healthy: 3,
}

function SourceTable({ sources }: { sources: IngestionSource[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const sorted = [...sources].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'status') {
      cmp = STATUS_ORDER[a.status] - STATUS_ORDER[b.status]
    } else {
      const aAge = a.age_seconds ?? Infinity
      const bAge = b.age_seconds ?? Infinity
      cmp = aAge - bAge
    }
    return sortDir === 'asc' ? cmp : -cmp
  })

  function SortHeader({ col, label }: { col: SortKey; label: string }) {
    const active = sortKey === col
    return (
      <th
        className="cursor-pointer select-none px-3 py-2 text-left text-xs font-medium text-muted-foreground hover:text-foreground"
        onClick={() => handleSort(col)}
      >
        {label}
        {active && (
          <span className="ml-1 text-xs">{sortDir === 'asc' ? '↑' : '↓'}</span>
        )}
      </th>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{sk.ingestion.tableSource}</th>
            <SortHeader col="status" label={sk.ingestion.tableStatus} />
            <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">{sk.ingestion.tableNotices}</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">{sk.ingestion.tableLast24h}</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">{sk.ingestion.tableLast7d}</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">{sk.ingestion.tableRegistry}</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">{sk.ingestion.tableSkips}</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">{sk.ingestion.tableDiskSize}</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{sk.ingestion.tableLastIngest}</th>
            <SortHeader col="age_seconds" label={sk.ingestion.tableAge} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((src) => (
            <tr key={src.name} className="border-b border-border last:border-0">
              <td className="px-3 py-2 font-mono font-medium">{src.name}</td>
              <td className="px-3 py-2">
                <span
                  data-testid={`status-badge-${src.name}`}
                  className={cn(
                    'inline-block rounded px-2 py-0.5 text-xs font-medium',
                    statusBadgeClass(src.status),
                  )}
                >
                  {statusLabel(src.status)}
                </span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{formatNumber(src.notices)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatNumber(src.last_24h)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatNumber(src.last_7d)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatNumber(src.registry)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatNumber(src.skips)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatBytes(src.disk_bytes)}</td>
              <td className="px-3 py-2 text-muted-foreground">
                {src.last_ingest_at ? formatSlovakDateTime(src.last_ingest_at) : '—'}
              </td>
              <td className="px-3 py-2 text-muted-foreground">{formatAge(src.age_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Page skeleton (loading state) ─────────────────────────────────────────────

function PageSkeleton() {
  return (
    <div className="space-y-6" data-testid="ingestion-skeleton">
      {/* header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <Skeleton className="h-6 w-64" />
          <Skeleton className="h-4 w-40" />
        </div>
        <Skeleton className="h-8 w-24" />
      </div>
      {/* kpi strip */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
      {/* table */}
      <SkeletonCard />
      {/* chart */}
      <Skeleton className="h-64 w-full rounded-lg" />
      {/* donut + dedup */}
      <div className="grid gap-6 md:grid-cols-2">
        <Skeleton className="h-48 rounded-lg" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
      {/* run card */}
      <Skeleton className="h-28 rounded-lg" />
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function IngestionPage() {
  const { data, isLoading, isError, error, refetch } = useIngestionDashboard()

  if (isLoading) return <PageSkeleton />

  if (isError) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-center">
        <p className="text-muted-foreground">{sk.ingestion.error}</p>
        {error instanceof Error && (
          <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
        )}
        <button
          onClick={() => void refetch()}
          className="mt-4 text-sm text-primary underline-offset-4 hover:underline"
        >
          {sk.common.retry}
        </button>
      </div>
    )
  }

  if (!data) return null

  const { totals, sources, timeseries, latest_run, generated_at } = data

  // KPI: registry drift
  const drift = totals.registry_entries - totals.notices
  const driftColor =
    Math.abs(drift) < 100
      ? 'text-green-700'
      : Math.abs(drift) < 1000
        ? 'text-yellow-700'
        : 'text-red-700'

  // KPI: sources healthy color
  const healthyRatio = totals.sources_healthy / totals.sources_total
  const healthyColor =
    healthyRatio === 1
      ? 'text-green-700'
      : healthyRatio >= 0.6
        ? 'text-yellow-700'
        : 'text-red-700'

  // Staleness alert
  const alertSources = sources.filter((s) => s.status === 'warning' || s.status === 'stale')
  const hasStale = alertSources.some((s) => s.status === 'stale')

  // Donut data
  const donutData = sources.map((s) => ({
    name: s.name,
    value: s.notices,
    color: SOURCE_COLORS[s.name as SourceName] ?? '#888',
  }))

  // Bar chart data: format date label
  const barData = timeseries.daily_ingestion.map((bucket) => ({
    ...bucket,
    dateLabel: formatShortDate(bucket.date),
  }))

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{sk.ingestion.title}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {sk.ingestion.subtitle}: {formatSlovakDateTime(generated_at)}
          </p>
        </div>
        <button
          onClick={() => void refetch()}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm text-foreground hover:bg-accent"
        >
          {sk.ingestion.refresh}
        </button>
      </div>

      {/* KPI strip */}
      <div
        data-testid="kpi-strip"
        className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6"
      >
        <KpiTile
          label={sk.ingestion.kpiNotices}
          value={formatNumber(totals.notices)}
        />
        <KpiTile
          label={sk.ingestion.kpiSourcesHealthy}
          value={
            <span className={healthyColor}>
              {totals.sources_healthy}/{totals.sources_total}
            </span>
          }
        />
        <KpiTile
          label={sk.ingestion.kpiLastRunAge}
          value={formatAge(totals.last_run_age_seconds)}
        />
        <KpiTile
          label={sk.ingestion.kpiDedupRate}
          value={
            totals.dedup_match_rate === 0 ? (
              <span
                className="text-red-700"
                title={sk.ingestion.dedupWarningTooltip}
              >
                {formatPercent(totals.dedup_match_rate)} %
              </span>
            ) : (
              `${formatPercent(totals.dedup_match_rate)} %`
            )
          }
        />
        <KpiTile
          label={sk.ingestion.kpiCrossMatches}
          value={formatNumber(totals.cross_source_matches)}
        />
        <KpiTile
          label={sk.ingestion.kpiRegistryDrift}
          value={<span className={driftColor}>{formatNumber(drift)}</span>}
        />
      </div>

      {/* Staleness alert banner */}
      {alertSources.length > 0 && (
        <div
          data-testid="stale-banner"
          className={cn(
            'rounded-lg border px-4 py-3 text-sm',
            hasStale
              ? 'border-red-200 bg-red-50 text-red-800'
              : 'border-yellow-200 bg-yellow-50 text-yellow-800',
          )}
        >
          <span className="font-medium">{sk.ingestion.staleBannerTitle}: </span>
          {alertSources.map((s, i) => (
            <span key={s.name}>
              {i > 0 && ', '}
              <span className="font-mono">{s.name}</span>
              {s.age_seconds !== null && ` (${formatAge(s.age_seconds)})`}
            </span>
          ))}
        </div>
      )}

      {/* Per-source health table */}
      <SectionCard>
        <SectionTitle>{sk.ingestion.tableSource}</SectionTitle>
        <SourceTable sources={sources} />
      </SectionCard>

      {/* Daily ingestion chart */}
      <SectionCard>
        <SectionTitle>{sk.ingestion.chartTitle}</SectionTitle>
        <div data-testid="daily-chart">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={barData}
              margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis
                dataKey="dateLabel"
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip
                formatter={(value: number, name: string) => [formatNumber(value), name]}
                labelFormatter={(label: string, payload) => {
                  if (payload && payload[0]) {
                    const bucket = payload[0].payload as { date: string }
                    return bucket.date
                  }
                  return label
                }}
              />
              {SOURCE_NAMES.map((src) => (
                <Bar
                  key={src}
                  dataKey={src}
                  stackId="a"
                  fill={SOURCE_COLORS[src]}
                  name={src}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>

      {/* Donut + dedup card */}
      <div className="grid gap-6 md:grid-cols-2">
        <SectionCard>
          <SectionTitle>{sk.ingestion.donutTitle}</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={donutData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={2}
              >
                {donutData.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => formatNumber(v)} />
              <Legend
                layout="vertical"
                align="right"
                verticalAlign="middle"
                iconSize={10}
              />
            </PieChart>
          </ResponsiveContainer>
        </SectionCard>

        <SectionCard>
          <SectionTitle>{sk.ingestion.dedupCardTitle}</SectionTitle>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">{sk.ingestion.dedupCardMatches}</dt>
              <dd className="tabular-nums font-medium">{formatNumber(totals.cross_source_matches)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">{sk.ingestion.dedupCardLinked}</dt>
              <dd className="tabular-nums font-medium">{formatNumber(totals.canonical_linked)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">{sk.ingestion.dedupCardRate}</dt>
              <dd className="tabular-nums font-medium">{formatPercent(totals.dedup_match_rate)} %</dd>
            </div>
          </dl>
          {totals.cross_source_matches === 0 && totals.notices > 0 && (
            <div
              data-testid="dedup-warning"
              className="mt-4 rounded border border-yellow-200 bg-yellow-50 px-3 py-2 text-sm text-yellow-800"
            >
              {sk.ingestion.dedupCardWarning}
            </div>
          )}
        </SectionCard>
      </div>

      {/* Latest run card */}
      <SectionCard>
        <SectionTitle>{sk.ingestion.latestRunTitle}</SectionTitle>
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted-foreground">{sk.ingestion.latestRunId}</dt>
            {latest_run.id ? (
              <dd
                className="mt-0.5 cursor-pointer font-mono text-xs text-foreground"
                title={latest_run.id}
                onClick={() => void navigator.clipboard?.writeText(latest_run.id!)}
              >
                {latest_run.id.slice(0, 8)}…
              </dd>
            ) : (
              <dd className="mt-0.5 font-mono text-xs text-muted-foreground">—</dd>
            )}
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{sk.ingestion.latestRunStarted}</dt>
            <dd className="mt-0.5 text-xs text-foreground">
              {latest_run.started_at ? formatSlovakDateTime(latest_run.started_at) : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{sk.ingestion.latestRunFinished}</dt>
            <dd className="mt-0.5 text-xs text-foreground">
              {latest_run.finished_at
                ? formatSlovakDateTime(latest_run.finished_at)
                : sk.ingestion.latestRunFinishedNever}
            </dd>
          </div>
        </dl>
      </SectionCard>

      {/* Worker status */}
      <WorkerStatusTable />

      {/* Ingestion event log */}
      <IngestionLogPanel />
    </div>
  )
}

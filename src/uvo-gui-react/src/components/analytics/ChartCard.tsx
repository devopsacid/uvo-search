import { useId, useState } from 'react'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Skeleton'
import { DataTableToggle } from '@/components/analytics/DataTableToggle'
import { useAnalyticsFilters } from '@/hooks/useAnalyticsFilters'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

/** The subset of a TanStack Query result the card needs. */
export interface ChartQueryState {
  isLoading: boolean
  isError: boolean
  error: unknown
  isFetching?: boolean
  refetch: () => unknown
}

interface ChartCardProps {
  title: string
  /** Effective period / scope line under the title. */
  caption?: string
  /** One sentence summarising the data for screen readers (role="img" label). */
  ariaLabel: string
  status: ChartQueryState
  isEmpty: boolean
  /** The graphic. */
  chart: React.ReactNode
  /** The same data as a semantic table; enables the toggle. */
  table?: React.ReactNode
  onExportCsv?: () => void
  /** Extra controls (metric switch, granularity select) shown next to the toggle. */
  actions?: React.ReactNode
  /** Set false when the chart markup is already semantic (a list of links) and must not become role="img". */
  asImage?: boolean
  /** Hide the "widen period / clear filters" empty-state action (pages that ignore filters). */
  hideEmptyAction?: boolean
  skeletonClassName?: string
  className?: string
  children?: never
}

export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const message = error instanceof Error ? error.message : ''
  const isTimeout = message === 'analytics_timeout'
  return (
    <div role="alert" className="rounded-md border border-border bg-muted/40 p-4 text-sm">
      <p className="font-medium text-foreground">{sk.analytics.charts.errorTitle}</p>
      <p className="mt-1 text-muted-foreground">
        {isTimeout ? sk.analytics.charts.timeout : message || sk.common.error}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {sk.analytics.charts.retry}
      </button>
    </div>
  )
}

function EmptyBody({ hideAction }: { hideAction: boolean }) {
  const { isDefault, preset, applyPreset, reset, filters } = useAnalyticsFilters()
  const hasEntityFilters = Boolean(filters.cpv || filters.source || filters.procurer_ico || filters.supplier_ico)
  let action: React.ReactNode
  if (!hideAction && !isDefault) {
    // Entity filters narrow the data more than the period does, so clearing them comes first.
    const clear = hasEntityFilters || preset === 'last5'
    action = (
      <button
        type="button"
        onClick={() => (clear ? reset() : applyPreset('last5'))}
        className="text-sm text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {clear ? sk.common.clearFilters : sk.analytics.charts.widenPeriod}
      </button>
    )
  }
  return (
    <EmptyState
      title={sk.analytics.charts.emptyTitle}
      description={sk.analytics.charts.emptyHint}
      action={action}
      className="py-10"
    />
  )
}

export function ChartCard({
  title,
  caption,
  ariaLabel,
  status,
  isEmpty,
  chart,
  table,
  onExportCsv,
  actions,
  asImage = true,
  hideEmptyAction = false,
  skeletonClassName = 'h-64',
  className,
}: ChartCardProps) {
  const [showTable, setShowTable] = useState(false)
  const bodyId = useId()
  const loading = status.isLoading
  const hasData = !loading && !status.isError && !isEmpty
  const refreshing = Boolean(status.isFetching) && !loading

  let body: React.ReactNode
  if (loading) {
    body = (
      <div role="status" aria-label={sk.analytics.charts.loading}>
        <Skeleton className={cn('w-full', skeletonClassName)} />
      </div>
    )
  } else if (status.isError) {
    body = <ErrorPanel error={status.error} onRetry={() => void status.refetch()} />
  } else if (isEmpty) {
    body = <EmptyBody hideAction={hideEmptyAction} />
  } else if (showTable && table) {
    body = table
  } else if (asImage) {
    body = (
      <div role="img" aria-label={ariaLabel}>
        {chart}
      </div>
    )
  } else {
    body = chart
  }

  return (
    <figure className={cn('rounded-lg border border-border bg-card p-4', className)}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <figcaption className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {caption && <p className="mt-0.5 text-xs text-muted-foreground">{caption}</p>}
        </figcaption>
        <div className="flex flex-wrap items-center gap-2">
          {refreshing && (
            <span
              role="status"
              className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
            >
              {sk.analytics.charts.updating}
            </span>
          )}
          {actions}
          {hasData && table && (
            <DataTableToggle showTable={showTable} onToggle={() => setShowTable((v) => !v)} controls={bodyId} />
          )}
          {onExportCsv && (
            <button
              type="button"
              onClick={onExportCsv}
              disabled={!hasData}
              className="rounded-md border border-border px-2.5 py-1 text-xs text-foreground hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sk.analytics.charts.exportCsv}
            </button>
          )}
        </div>
      </div>
      <div id={bodyId}>{body}</div>
    </figure>
  )
}

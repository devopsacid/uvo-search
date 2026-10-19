import { Link } from 'react-router-dom'
import { KpiCard } from '@/components/ui/KpiCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatPercent } from '@/lib/utils'
import sk from '@/i18n/sk'

export interface KpiItem {
  key: string
  label: string
  value: string
  /** Change vs the previous period in percent; null/undefined = no comparison. Omit for non-comparable KPIs. */
  deltaPct?: number | null
  showDelta?: boolean
  /** Click target (contract list or entity view). */
  href?: string
  title?: string
  /** Extra content under the value (e.g. a band chip). */
  extra?: React.ReactNode
}

interface KpiRowProps {
  items: KpiItem[]
  isLoading?: boolean
  /** Number of placeholder tiles while loading. */
  skeletonCount?: number
  columnsClassName?: string
}

function Delta({ pct }: { pct: number | null | undefined }) {
  if (pct == null) {
    return <p className="mt-1 text-xs text-muted-foreground">{sk.analytics.kpi.noComparison}</p>
  }
  const arrow = pct > 0 ? '↑' : pct < 0 ? '↓' : '→'
  const signed = `${pct > 0 ? '+' : ''}${formatPercent(pct)}`
  return (
    <p className="mt-1 text-xs text-muted-foreground">
      <span aria-hidden="true">{arrow} </span>
      <span className="font-medium text-foreground tabular-nums">{signed}</span> {sk.analytics.kpi.deltaVsPrevious}
    </p>
  )
}

const CARD_RESET = 'rounded-none border-0 bg-transparent p-0'
const TILE = 'block rounded-lg border border-border bg-card p-4'

export function KpiRow({
  items,
  isLoading,
  skeletonCount = 5,
  columnsClassName = 'grid-cols-2 lg:grid-cols-5',
}: KpiRowProps) {
  if (isLoading) {
    return (
      <div className={`grid gap-4 ${columnsClassName}`} role="status" aria-label={sk.analytics.charts.loading}>
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    )
  }
  return (
    <ul className={`grid gap-4 ${columnsClassName}`}>
      {items.map((item) => {
        const inner = (
          <>
            <KpiCard label={item.label} value={item.value} className={CARD_RESET} />
            {item.extra && <div className="mt-1">{item.extra}</div>}
            {item.showDelta && <Delta pct={item.deltaPct} />}
          </>
        )
        return (
          <li key={item.key} title={item.title}>
            {item.href ? (
              <Link
                to={item.href}
                className={`${TILE} hover:bg-accent/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring`}
              >
                {inner}
              </Link>
            ) : (
              <div className={TILE}>{inner}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

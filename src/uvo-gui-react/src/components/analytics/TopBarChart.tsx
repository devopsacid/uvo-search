import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

export interface TopBarRow {
  key: string
  label: string
  /** Bar length basis (value or count). */
  amount: number
  /** Already formatted amount, e.g. "12,3 M €". */
  amountLabel: string
  sharePct: number
  shareLabel: string
  /** Bar / row drill-down target (the contract list). */
  href?: string
  /** Name link (entity workspace); omitted for CPV buckets and "Ostatné". */
  profileHref?: string
  muted?: boolean
}

interface TopBarChartProps {
  rows: TopBarRow[]
  ariaLabel: string
}

/**
 * Horizontal ranked bars built from native links, so every bar is keyboard-focusable and
 * activates with Enter (and works with screen readers) without bespoke key handling.
 */
export function TopBarChart({ rows, ariaLabel }: TopBarChartProps) {
  const max = Math.max(1, ...rows.map((r) => r.amount))
  return (
    <ol aria-label={ariaLabel} className="space-y-2">
      {rows.map((r) => {
        const width = Math.max(1.5, (r.amount / max) * 100)
        const bar = (
          <span className="flex items-center gap-3">
            <span className="relative block h-5 flex-1 overflow-hidden rounded-sm bg-muted" aria-hidden="true">
              <span
                className={cn('absolute inset-y-0 left-0 rounded-sm', r.muted ? 'bg-slate-500' : 'bg-primary')}
                style={{ width: `${width}%` }}
              />
            </span>
            <span className="w-40 shrink-0 text-right text-xs tabular-nums text-foreground">
              {r.amountLabel}
              <span className="ml-1.5 text-muted-foreground">{r.shareLabel}</span>
            </span>
          </span>
        )
        return (
          <li key={r.key} className="grid gap-x-3 gap-y-0.5 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)] sm:items-center">
            <span className="min-w-0 truncate text-sm" title={r.label}>
              {r.profileHref ? (
                <Link to={r.profileHref} className="text-primary underline-offset-2 hover:underline">
                  {r.label}
                </Link>
              ) : (
                <span className={r.muted ? 'text-muted-foreground' : 'text-foreground'}>{r.label}</span>
              )}
            </span>
            {r.href ? (
              <Link
                to={r.href}
                aria-label={`${sk.analytics.charts.showContracts}: ${r.label}, ${r.amountLabel}, ${r.shareLabel}`}
                className="block rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring hover:opacity-80"
              >
                {bar}
              </Link>
            ) : (
              <span className="block">{bar}</span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

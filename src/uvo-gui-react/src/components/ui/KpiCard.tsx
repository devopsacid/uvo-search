import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

interface KpiCardProps {
  label: string
  value: string
  pct?: number | null
  className?: string
  /** Period-over-period delta (fraction, not percent — 0.12 = +12%). */
  delta?: number | null
  /** Label shown next to delta. Defaults to "vs. predchadzajuce obdobie". */
  deltaLabel?: string
  /** Small secondary text under the value (e.g. coverage warning). */
  subtext?: string
  /** When true, renders a larger value font for executive pages. */
  large?: boolean
}

export function KpiCard({
  label,
  value,
  pct,
  className,
  delta,
  deltaLabel,
  subtext,
  large,
}: KpiCardProps) {
  const hasDelta = delta !== undefined
  const deltaDisplay = (() => {
    if (!hasDelta || delta === null) return null
    const sign = delta >= 0 ? '+' : ''
    const pctStr = `${sign}${(delta * 100).toFixed(1)} %`
    return { pctStr, positive: delta >= 0 }
  })()

  return (
    <div className={cn('rounded-lg border border-border bg-card p-4', className)}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p
        className={cn(
          'mt-1 tabular-nums font-semibold text-foreground',
          large ? 'text-3xl' : 'text-2xl',
        )}
      >
        {value}
      </p>
      {subtext && (
        <p className="mt-0.5 text-xs text-muted-foreground">{subtext}</p>
      )}
      {deltaDisplay && (
        <p
          className={cn(
            'mt-1 text-xs',
            deltaDisplay.positive ? 'text-green-600' : 'text-red-600',
          )}
        >
          {deltaDisplay.pctStr}{' '}
          <span className="text-muted-foreground">
            {deltaLabel ?? sk.analytics.common.vsPreview}
          </span>
        </p>
      )}
      {hasDelta && delta === null && (
        <p className="mt-1 text-xs text-muted-foreground">{sk.analytics.common.noDelta}</p>
      )}
      {pct != null && (
        <p className={cn('mt-1 text-xs', pct >= 0 ? 'text-green-600' : 'text-red-600')}>
          {pct >= 0 ? '+' : ''}{pct} % YoY
        </p>
      )}
    </div>
  )
}

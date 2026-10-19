import { seriesColor } from '@/components/analytics/palette'

export interface ShareSegment {
  key: string
  label: string
  sharePct: number
  /** Formatted share for the legend, e.g. "12,3 %". */
  shareLabel: string
}

interface ShareStackBarProps {
  segments: ShareSegment[]
}

/** A single 100 % stacked bar; segments are labelled in the legend (never colour-only). */
export function ShareStackBar({ segments }: ShareStackBarProps) {
  const total = segments.reduce((sum, s) => sum + Math.max(0, s.sharePct), 0) || 1
  return (
    <div>
      <div className="flex h-8 w-full overflow-hidden rounded-md bg-muted">
        {segments.map((s, i) => (
          <div
            key={s.key}
            title={`${s.label}: ${s.shareLabel}`}
            style={{ width: `${(Math.max(0, s.sharePct) / total) * 100}%`, backgroundColor: seriesColor(i, s.key) }}
            className="h-full border-r border-card last:border-r-0"
          />
        ))}
      </div>
      <ul className="mt-3 grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2 lg:grid-cols-3">
        {segments.map((s, i) => (
          <li key={s.key} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="h-3 w-3 shrink-0 rounded-sm"
              style={{ backgroundColor: seriesColor(i, s.key) }}
            />
            <span className="min-w-0 flex-1 truncate text-foreground" title={s.label}>
              {s.label}
            </span>
            <span className="tabular-nums text-muted-foreground">{s.shareLabel}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

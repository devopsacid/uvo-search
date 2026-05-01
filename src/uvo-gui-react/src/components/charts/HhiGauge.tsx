import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

interface HhiGaugeProps {
  hhi: number
  top1SharePct?: number
  top3SharePct?: number
  className?: string
}

type Risk = 'low' | 'medium' | 'high'

// HHI is delivered as a 0–1 fraction (sum of squared share fractions).
// Industry convention reports HHI on a 0–10000 scale; display reflects that,
// with risk thresholds at the standard 0.15 / 0.40 cut points.
function getRisk(hhi: number): Risk {
  if (hhi < 0.15) return 'low'
  if (hhi < 0.4) return 'medium'
  return 'high'
}

const riskLabel: Record<Risk, string> = {
  low: sk.analytics.common.hhiLow,
  medium: sk.analytics.common.hhiMedium,
  high: sk.analytics.common.hhiHigh,
}

const arcFill: Record<Risk, string> = {
  low: '#16a34a',
  medium: '#d97706',
  high: '#dc2626',
}

const textColor: Record<Risk, string> = {
  low: 'text-green-600',
  medium: 'text-amber-600',
  high: 'text-red-600',
}

/** Semicircular SVG gauge. HHI is a 0–1 fraction; displayed on the 0–10000 scale. */
export function HhiGauge({ hhi, top1SharePct, top3SharePct, className }: HhiGaugeProps) {
  const risk = getRisk(hhi)
  const fraction = Math.min(Math.max(hhi, 0), 1)

  // SVG semicircle: cx=60, cy=60, r=50, from 180° to 0°
  const cx = 60
  const cy = 60
  const r = 50
  // Full arc: half circle (180 deg)
  // Angle: starts at π (left), ends at 0 (right)
  // Fraction maps 0→left, 1→right
  const startAngle = Math.PI
  const endAngle = startAngle - fraction * Math.PI
  const x1 = cx + r * Math.cos(startAngle)
  const y1 = cy + r * Math.sin(startAngle)
  const x2 = cx + r * Math.cos(endAngle)
  const y2 = cy + r * Math.sin(endAngle)
  const largeArc = fraction > 0.5 ? 1 : 0

  return (
    <div className={cn('space-y-3', className)}>
      <div className="relative mx-auto w-32">
        <svg viewBox="0 0 120 65" className="w-full overflow-visible">
          {/* Track */}
          <path
            d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
            fill="none"
            stroke="hsl(var(--muted))"
            strokeWidth="10"
            strokeLinecap="round"
          />
          {/* Fill arc */}
          {fraction > 0 && (
            <path
              d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 0 ${x2} ${y2}`}
              fill="none"
              stroke={arcFill[risk]}
              strokeWidth="10"
              strokeLinecap="round"
            />
          )}
          {/* Numeric value */}
          <text
            x={cx}
            y={cy - 4}
            textAnchor="middle"
            fontSize="16"
            fontWeight="700"
            fill={arcFill[risk]}
          >
            {(hhi * 10000).toFixed(0)}
          </text>
          <text
            x={cx}
            y={cy + 10}
            textAnchor="middle"
            fontSize="9"
            fill="hsl(var(--muted-foreground))"
          >
            {sk.analytics.common.hhi}
          </text>
        </svg>
      </div>
      <p className={cn('text-center text-xs font-medium', textColor[risk])}>{riskLabel[risk]}</p>
      {(top1SharePct !== undefined || top3SharePct !== undefined) && (
        <div className="flex justify-around text-center text-xs text-muted-foreground">
          {top1SharePct !== undefined && (
            <span>
              <span className="block text-sm font-semibold text-foreground tabular-nums">
                {(top1SharePct * 100).toFixed(1)} %
              </span>
              {sk.analytics.common.top1Share}
            </span>
          )}
          {top3SharePct !== undefined && (
            <span>
              <span className="block text-sm font-semibold text-foreground tabular-nums">
                {(top3SharePct * 100).toFixed(1)} %
              </span>
              {sk.analytics.common.top3Share}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

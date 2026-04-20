import { cn } from '@/lib/utils'

interface GaugeProps {
  value: number // 0..10000
  label: string
  riskLabel: string
  riskClass: 'low' | 'medium' | 'high'
}

const riskStyles = {
  low: 'text-green-600',
  medium: 'text-yellow-600',
  high: 'text-red-600',
}

const riskBarStyles = {
  low: 'bg-green-500',
  medium: 'bg-yellow-500',
  high: 'bg-red-500',
}

export function Gauge({ value, label, riskLabel, riskClass }: GaugeProps) {
  const pct = Math.min(value / 10000, 1) * 100

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className={cn('text-xl font-bold tabular-nums', riskStyles[riskClass])}>
          {value.toFixed(0)}
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-all', riskBarStyles[riskClass])}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className={cn('text-xs font-medium', riskStyles[riskClass])}>{riskLabel}</p>
    </div>
  )
}

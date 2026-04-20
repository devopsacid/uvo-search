import { cn } from '@/lib/utils'

interface KpiCardProps {
  label: string
  value: string
  pct?: number | null
  className?: string
}

export function KpiCard({ label, value, pct, className }: KpiCardProps) {
  return (
    <div className={cn('rounded-lg border border-border bg-card p-4', className)}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
      {pct != null && (
        <p className={cn('mt-1 text-xs', pct >= 0 ? 'text-green-600' : 'text-red-600')}>
          {pct >= 0 ? '+' : ''}{pct} % YoY
        </p>
      )}
    </div>
  )
}

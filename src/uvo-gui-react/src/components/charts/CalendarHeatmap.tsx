import type { MonthBucket } from '@/api/types'
import { cn } from '@/lib/utils'

interface CalendarHeatmapProps {
  data: MonthBucket[]
  monthNames: string[]
  onCellClick?: (month: number) => void
}

function intensity(count: number, max: number): string {
  if (!max || count === 0) return 'bg-muted'
  const ratio = count / max
  if (ratio > 0.75) return 'bg-primary'
  if (ratio > 0.5) return 'bg-primary/70'
  if (ratio > 0.25) return 'bg-primary/40'
  return 'bg-primary/20'
}

export function CalendarHeatmap({ data, monthNames, onCellClick }: CalendarHeatmapProps) {
  const max = Math.max(...data.map((d) => d.contract_count), 1)

  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
      {data.map((bucket) => {
        const label = monthNames[bucket.month - 1] ?? String(bucket.month)
        return (
          <button
            key={bucket.month}
            onClick={() => onCellClick?.(bucket.month)}
            className={cn(
              'flex flex-col items-center justify-center rounded-lg p-4 text-center transition-opacity hover:opacity-80',
              intensity(bucket.contract_count, max),
              bucket.contract_count > 0 ? 'cursor-pointer' : 'cursor-default opacity-60',
            )}
          >
            <span className="text-xs font-medium text-foreground">{label}</span>
            <span className="mt-1 text-lg font-semibold tabular-nums text-foreground">
              {bucket.contract_count}
            </span>
          </button>
        )
      })}
    </div>
  )
}

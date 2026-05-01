import { cn } from '@/lib/utils'
import type { Anomaly, AnomalySeverity } from '@/api/types'

const severityStyles: Record<AnomalySeverity, string> = {
  info: 'border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200',
  warn: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200',
  critical:
    'border-red-200 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200',
}

const dotStyles: Record<AnomalySeverity, string> = {
  info: 'bg-blue-500',
  warn: 'bg-amber-500',
  critical: 'bg-red-500',
}

interface AnomalyBannerProps {
  anomalies: Anomaly[]
  /** Max items to show, defaults to 3. */
  max?: number
}

export function AnomalyBanner({ anomalies, max = 3 }: AnomalyBannerProps) {
  if (!anomalies.length) return null

  const visible = anomalies.slice(0, max)

  return (
    <div className="space-y-2 print:space-y-1">
      {visible.map((a) => (
        <div
          key={a.code}
          className={cn('flex gap-3 rounded-lg border px-4 py-3', severityStyles[a.severity])}
        >
          <span
            className={cn(
              'mt-1 h-2 w-2 shrink-0 rounded-full',
              dotStyles[a.severity],
            )}
          />
          <div className="min-w-0">
            <p className="text-sm font-medium">{a.title_sk}</p>
            <p className="mt-0.5 text-xs opacity-80">{a.detail_sk}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

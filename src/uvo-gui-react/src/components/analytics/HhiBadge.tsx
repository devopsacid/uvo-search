import type { HhiBand } from '@/api/types'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

const STYLES: Record<HhiBand, string> = {
  low: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  moderate: 'bg-amber-50 text-amber-900 border-amber-200',
  high: 'bg-rose-50 text-rose-800 border-rose-200',
}

/** Band chip with a text label (never colour-only) and the threshold explanation as tooltip. */
export function HhiBadge({ band }: { band: HhiBand }) {
  const text = sk.analytics.koncentracia.bands[band]
  return (
    <span
      title={sk.analytics.koncentracia.bandHint[band]}
      className={cn('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium', STYLES[band])}
    >
      {text}
    </span>
  )
}

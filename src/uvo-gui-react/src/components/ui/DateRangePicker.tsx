import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

export interface DateRange {
  dateFrom: string
  dateTo: string
}

type Preset = 'last30d' | 'last12m' | 'ytd' | 'prevYear'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function subtractDays(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

function resolvePreset(preset: Preset): DateRange {
  const today = todayIso()
  const year = new Date().getFullYear()
  switch (preset) {
    case 'last30d':
      return { dateFrom: subtractDays(30), dateTo: today }
    case 'last12m':
      return { dateFrom: subtractDays(365), dateTo: today }
    case 'ytd':
      return { dateFrom: `${year}-01-01`, dateTo: today }
    case 'prevYear':
      return { dateFrom: `${year - 1}-01-01`, dateTo: `${year - 1}-12-31` }
  }
}

const PRESETS: { id: Preset; label: string }[] = [
  { id: 'last30d', label: sk.analytics.common.preset30d },
  { id: 'last12m', label: sk.analytics.common.preset12m },
  { id: 'ytd', label: sk.analytics.common.presetYtd },
  { id: 'prevYear', label: sk.analytics.common.presetPrevYear },
]

interface DateRangePickerProps {
  className?: string
}

export function DateRangePicker({ className }: DateRangePickerProps) {
  const [searchParams, setSearchParams] = useSearchParams()

  const dateFrom = searchParams.get('date_from') ?? ''
  const dateTo = searchParams.get('date_to') ?? ''

  const setRange = useCallback(
    (from: string, to: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('date_from', from)
          next.set('date_to', to)
          return next
        },
        { replace: false },
      )
    },
    [setSearchParams],
  )

  function applyPreset(preset: Preset) {
    const { dateFrom: f, dateTo: t } = resolvePreset(preset)
    setRange(f, t)
  }

  function isActivePreset(preset: Preset): boolean {
    const { dateFrom: f, dateTo: t } = resolvePreset(preset)
    return f === dateFrom && t === dateTo
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <div className="flex items-center gap-1.5">
        <label className="text-xs text-muted-foreground whitespace-nowrap">
          {sk.analytics.common.dateFrom}
        </label>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setRange(e.target.value, dateTo)}
          className="rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div className="flex items-center gap-1.5">
        <label className="text-xs text-muted-foreground whitespace-nowrap">
          {sk.analytics.common.dateTo}
        </label>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setRange(dateFrom, e.target.value)}
          className="rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div className="flex flex-wrap gap-1">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => applyPreset(p.id)}
            className={cn(
              'rounded px-2 py-1 text-xs transition-colors',
              isActivePreset(p.id)
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground',
            )}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Returns the current date_from / date_to from URL, falling back to last 12 months. */
export function useDateRange(): DateRange {
  const [searchParams] = useSearchParams()
  const today = todayIso()
  const defaultFrom = subtractDays(365)

  return {
    dateFrom: searchParams.get('date_from') ?? defaultFrom,
    dateTo: searchParams.get('date_to') ?? today,
  }
}

import { filtersToParams, periodRange, type AnalyticsFilters } from '@/lib/analyticsFilters'

type Extra = Partial<Record<string, string | undefined>>

/**
 * Drill-down target: `/zakazky` accepts the same param names as the filter bar, so this is
 * a pure param copy plus the clicked entity/bucket in `extra` (which overrides the filters).
 */
export function zakazkyLink(filters: AnalyticsFilters, extra: Extra = {}): string {
  const qs = filtersToParams(filters, extra).toString()
  return qs ? `/zakazky?${qs}` : '/zakazky'
}

/** Drill-down for a time bucket ("2024-03", "2024-Q1", "2024"): narrows the date range. */
export function zakazkyPeriodLink(filters: AnalyticsFilters, period: string, extra: Extra = {}): string {
  const range = periodRange(period)
  return zakazkyLink(filters, { ...extra, ...(range ?? {}) })
}

export function firmaLink(ico: string): string {
  return `/firma/${encodeURIComponent(ico)}`
}

/** Link into a dashboard page carrying a set of filters. */
export function analyticsLink(
  page: 'prehlad' | 'koncentracia' | 'cpv' | 'pokrytie',
  filters: Partial<AnalyticsFilters> = {},
): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) if (v) params.set(k, v)
  const qs = params.toString()
  return `/analytika/${page}${qs ? `?${qs}` : ''}`
}

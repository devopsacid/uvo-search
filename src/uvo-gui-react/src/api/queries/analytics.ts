import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type {
  AnalyticsConcentration,
  AnalyticsConcentrationDimension,
  AnalyticsCoverage,
  AnalyticsCpv,
  AnalyticsCpvLevel,
  AnalyticsGranularity,
  AnalyticsSummary,
  AnalyticsTimeseries,
  AnalyticsTop,
  AnalyticsTopDimension,
  AnalyticsTopMetric,
} from '../types'
import { filtersToParams, validateRange, type AnalyticsFilters } from '@/lib/analyticsFilters'

/** Matches the server TTL (spec §7.3). */
export const ANALYTICS_STALE_TIME = 15 * 60 * 1000
const MAX_HHI_YEARS = 15

type Extra = Record<string, string | undefined>

/**
 * Keys use the *effective* filters (defaults applied), so a bare `/analytika/prehlad` and the
 * same view with explicit default dates share one cache entry.
 */
export const analyticsKeys = {
  all: ['analytics'] as const,
  summary: (f: AnalyticsFilters) => [...analyticsKeys.all, 'summary', f] as const,
  timeseries: (f: AnalyticsFilters, extra: Extra) => [...analyticsKeys.all, 'timeseries', f, extra] as const,
  top: (f: AnalyticsFilters, extra: Extra) => [...analyticsKeys.all, 'top', f, extra] as const,
  concentration: (f: AnalyticsFilters, dimension: string) =>
    [...analyticsKeys.all, 'concentration', f, dimension] as const,
  cpv: (f: AnalyticsFilters, level: string) => [...analyticsKeys.all, 'cpv', f, level] as const,
  coverage: () => [...analyticsKeys.all, 'coverage'] as const,
}

function path(endpoint: string, f: AnalyticsFilters, extra: Extra = {}): string {
  return `/analytics/${endpoint}?${filtersToParams(f, extra).toString()}`
}

interface HookOptions {
  /** Extra gate, e.g. wait for another query. The range validity gate is always applied. */
  enabled?: boolean
}

const common = {
  staleTime: ANALYTICS_STALE_TIME,
  placeholderData: keepPreviousData,
}

export function useAnalyticsSummary(f: AnalyticsFilters, opts: HookOptions = {}) {
  return useQuery({
    ...common,
    queryKey: analyticsKeys.summary(f),
    queryFn: ({ signal }) => apiClient.get<AnalyticsSummary>(path('summary', f), { signal }),
    enabled: !validateRange(f) && (opts.enabled ?? true),
  })
}

export function useAnalyticsTimeseries(
  f: AnalyticsFilters,
  p: { granularity: AnalyticsGranularity; split_by?: 'source' | 'cpv_division'; top?: number },
  opts: HookOptions = {},
) {
  const extra: Extra = {
    granularity: p.granularity,
    split_by: p.split_by,
    top: p.split_by && p.top ? String(p.top) : undefined,
  }
  return useQuery({
    ...common,
    queryKey: analyticsKeys.timeseries(f, extra),
    queryFn: ({ signal }) => apiClient.get<AnalyticsTimeseries>(path('timeseries', f, extra), { signal }),
    enabled: !validateRange(f) && (opts.enabled ?? true),
  })
}

export function useAnalyticsTop(
  f: AnalyticsFilters,
  p: { dimension: AnalyticsTopDimension; metric?: AnalyticsTopMetric; n?: number },
  opts: HookOptions = {},
) {
  const extra: Extra = { dimension: p.dimension, metric: p.metric ?? 'total_value', n: String(p.n ?? 10) }
  return useQuery({
    ...common,
    queryKey: analyticsKeys.top(f, extra),
    queryFn: ({ signal }) => apiClient.get<AnalyticsTop>(path('top', f, extra), { signal }),
    enabled: !validateRange(f) && (opts.enabled ?? true),
  })
}

export function useAnalyticsConcentration(
  f: AnalyticsFilters,
  dimension: AnalyticsConcentrationDimension = 'supplier',
  opts: HookOptions = {},
) {
  return useQuery({
    ...common,
    queryKey: analyticsKeys.concentration(f, dimension),
    queryFn: ({ signal }) =>
      apiClient.get<AnalyticsConcentration>(path('concentration', f, { dimension }), { signal }),
    enabled: !validateRange(f) && (opts.enabled ?? true),
  })
}

export function useAnalyticsCpv(f: AnalyticsFilters, level: AnalyticsCpvLevel = 'division', opts: HookOptions = {}) {
  return useQuery({
    ...common,
    queryKey: analyticsKeys.cpv(f, level),
    queryFn: ({ signal }) => apiClient.get<AnalyticsCpv>(path('cpv', f, { level }), { signal }),
    enabled: !validateRange(f) && (opts.enabled ?? true),
  })
}

/** Ignores filters server-side, so the key carries none. */
export function useAnalyticsCoverage() {
  return useQuery({
    ...common,
    queryKey: analyticsKeys.coverage(),
    queryFn: ({ signal }) => apiClient.get<AnalyticsCoverage>('/analytics/coverage', { signal }),
  })
}

/** One calendar year of the filtered range, clamped to the range itself. */
export interface YearSlice {
  year: number
  filters: AnalyticsFilters
}

export function yearSlices(f: AnalyticsFilters): YearSlice[] {
  const first = Number(f.date_from.slice(0, 4))
  const last = Number(f.date_to.slice(0, 4))
  const slices: YearSlice[] = []
  for (let year = Math.max(first, last - MAX_HHI_YEARS + 1); year <= last; year++) {
    const from = `${year}-01-01`
    const to = `${year}-12-31`
    slices.push({
      year,
      filters: { ...f, date_from: from > f.date_from ? from : f.date_from, date_to: to < f.date_to ? to : f.date_to },
    })
  }
  return slices
}

/** HHI per calendar year: one cached `/concentration` call per year, run in parallel (max 15). */
export function useConcentrationByYear(
  f: AnalyticsFilters,
  dimension: AnalyticsConcentrationDimension = 'supplier',
) {
  const slices = yearSlices(f)
  const valid = !validateRange(f)
  const results = useQueries({
    queries: slices.map((s) => ({
      ...common,
      queryKey: analyticsKeys.concentration(s.filters, dimension),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiClient.get<AnalyticsConcentration>(path('concentration', s.filters, { dimension }), { signal }),
      enabled: valid,
    })),
  })
  return { slices, results }
}

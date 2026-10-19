import { useCallback, useMemo } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import {
  FILTER_KEYS,
  activePreset,
  defaultRange,
  filtersToParams,
  isDefaultFilters,
  presetRange,
  resolveFilters,
  validateRange,
  type AnalyticsFilters,
  type FilterKey,
  type PresetId,
  type RangeProblem,
} from '@/lib/analyticsFilters'

export type FilterUpdate = Partial<Record<FilterKey, string | undefined>>

export interface UseAnalyticsFilters {
  /** Effective filters: URL values with defaults applied in memory. */
  filters: AnalyticsFilters
  /** Non-null when the range would be rejected by the API (queries are paused). */
  rangeProblem: RangeProblem | null
  isDefault: boolean
  preset: PresetId | null
  setFilters: (updates: FilterUpdate) => void
  applyPreset: (id: PresetId) => void
  reset: () => void
  /** Params for a drill-down link (effective filters + `extra`). */
  toSearchParams: (extra?: Partial<Record<string, string | undefined>>) => URLSearchParams
  /** Absolute URL of the current view, for "Kopírovať odkaz". */
  currentUrl: () => string
}

/**
 * URL-backed analytics filter state (spec §5.1). Defaults are applied in memory only and are
 * never written to the URL, so `/analytika/prehlad` stays short; changes push history entries.
 */
export function useAnalyticsFilters(): UseAnalyticsFilters {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  // "Today" is fixed per mount so effective query keys do not flip at midnight mid-session.
  const today = useMemo(() => new Date(), [])
  const filters = useMemo(() => resolveFilters(searchParams, today), [searchParams, today])

  const setFilters = useCallback(
    (updates: FilterUpdate) => {
      const def = defaultRange(today)
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        for (const key of FILTER_KEYS) {
          if (!(key in updates)) continue
          const value = updates[key]
          const isDefaultDate =
            (key === 'date_from' && value === def.date_from) || (key === 'date_to' && value === def.date_to)
          if (!value || isDefaultDate) next.delete(key)
          else next.set(key, value)
        }
        next.delete('page')
        return next
      })
    },
    [setSearchParams, today],
  )

  const applyPreset = useCallback(
    (id: PresetId) => setFilters(presetRange(id, today)),
    [setFilters, today],
  )

  const reset = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const key of FILTER_KEYS) next.delete(key)
      return next
    })
  }, [setSearchParams])

  const toSearchParams = useCallback(
    (extra: Partial<Record<string, string | undefined>> = {}) => filtersToParams(filters, extra),
    [filters],
  )

  const currentUrl = useCallback(
    () => `${window.location.origin}${location.pathname}${location.search}`,
    [location.pathname, location.search],
  )

  return {
    filters,
    rangeProblem: validateRange(filters),
    isDefault: isDefaultFilters(filters, today),
    preset: activePreset(filters, today),
    setFilters,
    applyPreset,
    reset,
    toSearchParams,
    currentUrl,
  }
}

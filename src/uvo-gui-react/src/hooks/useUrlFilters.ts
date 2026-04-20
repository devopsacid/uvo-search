import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Generic hook for reading/writing typed filter state via URL search params.
 * T is a flat record of string | number | undefined values.
 *
 * Back-button and shareable URL round-trips are free because we delegate
 * entirely to the browser's history via useSearchParams.
 */
export function useUrlFilters<T extends Record<string, string | number | undefined>>() {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = {} as T

  searchParams.forEach((value, key) => {
    ;(filters as Record<string, string>)[key] = value
  })

  const setFilters = useCallback(
    (updates: Partial<T>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [key, value] of Object.entries(updates)) {
            if (value === undefined || value === '' || value === null) {
              next.delete(key)
            } else {
              next.set(key, String(value))
            }
          }
          // Reset page when any non-page filter changes
          const hasNonPageChange = Object.keys(updates).some((k) => k !== 'page')
          if (hasNonPageChange && 'page' in updates === false) {
            next.delete('page')
          }
          return next
        },
        { replace: false },
      )
    },
    [setSearchParams],
  )

  const resetFilters = useCallback(() => {
    setSearchParams({}, { replace: false })
  }, [setSearchParams])

  const getParam = useCallback(
    (key: string, defaultValue?: string): string | undefined => {
      return searchParams.get(key) ?? defaultValue
    },
    [searchParams],
  )

  const getNumParam = useCallback(
    (key: string, defaultValue?: number): number | undefined => {
      const raw = searchParams.get(key)
      if (raw === null) return defaultValue
      const n = Number(raw)
      return isNaN(n) ? defaultValue : n
    },
    [searchParams],
  )

  return { filters, setFilters, resetFilters, getParam, getNumParam, searchParams }
}

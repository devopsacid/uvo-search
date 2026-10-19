import { QueryClient, type QueryClientConfig } from '@tanstack/react-query'
import { dashboardKeys } from './queries/dashboard'
import { firmaKeys } from './queries/firma'

const MINUTE = 60 * 1000

/** Default freshness for ordinary queries. */
export const DEFAULT_STALE_TIME = MINUTE
/** Aggregates change only when ingestion runs; keep them fresh for longer. */
export const AGGREGATE_STALE_TIME = 10 * MINUTE

/** Retry once on transient failures; client errors (4xx) will not heal by retrying. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status
  if (typeof status === 'number' && status >= 400 && status < 500) return false
  return failureCount < 1
}

type QueryDefaults = NonNullable<QueryClientConfig['defaultOptions']>['queries']

export function createQueryClient(overrides: QueryDefaults = {}): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        staleTime: DEFAULT_STALE_TIME,
        refetchOnWindowFocus: false,
        ...overrides,
      },
    },
  })
  // Per-hook staleTime still wins (e.g. "recent contracts" stays short). An explicit
  // staleTime override (tests) applies everywhere.
  if (overrides?.staleTime === undefined) {
    client.setQueryDefaults(dashboardKeys.all, { staleTime: AGGREGATE_STALE_TIME })
    client.setQueryDefaults(firmaKeys.all, { staleTime: AGGREGATE_STALE_TIME })
  }
  return client
}

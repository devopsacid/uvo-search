import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import { ingestionKeys } from './ingestion'
import type { IngestionLogResponse, IngestionLogLevel } from '../types'

// Foreground-only polling: paused while the tab is hidden (see refetchIntervalInBackground).
export const INGESTION_POLL_MS = 15_000

export interface UseIngestionLogParams {
  level?: IngestionLogLevel
  source?: string
  event?: string
  limit?: number
  offset?: number
}

export function useIngestionLog(params: UseIngestionLogParams = {}) {
  const search = new URLSearchParams()
  if (params.level) search.set('level', params.level)
  if (params.source) search.set('source', params.source)
  if (params.event) search.set('event', params.event)
  search.set('limit', String(params.limit ?? 50))
  search.set('offset', String(params.offset ?? 0))

  return useQuery({
    queryKey: ingestionKeys.log(params),
    queryFn: ({ signal }) =>
      apiClient.get<IngestionLogResponse>(`/dashboard/ingestion-log?${search}`, { signal }),
    placeholderData: (prev) => prev,
    refetchInterval: INGESTION_POLL_MS,
    refetchIntervalInBackground: false,
  })
}

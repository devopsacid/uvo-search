import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { IngestionLogResponse, IngestionLogLevel } from '../types'

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
    queryKey: ['ingestion-log', params],
    queryFn: () => apiClient.get<IngestionLogResponse>(`/dashboard/ingestion-log?${search}`),
    refetchInterval: 15_000,
  })
}

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { IngestionDashboard } from '../types'

export const ingestionKeys = {
  all: ['ingestion'] as const,
  dashboard: () => [...ingestionKeys.all, 'dashboard'] as const,
  log: (params: object) => [...ingestionKeys.all, 'log', params] as const,
  workerStatus: () => [...ingestionKeys.all, 'worker-status'] as const,
}

export function useIngestionDashboard() {
  return useQuery({
    queryKey: ingestionKeys.dashboard(),
    queryFn: ({ signal }) => apiClient.get<IngestionDashboard>('/dashboard/ingestion', { signal }),
    staleTime: 30 * 1000,
  })
}

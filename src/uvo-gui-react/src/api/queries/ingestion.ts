import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { IngestionDashboard } from '../types'

export const ingestionKeys = {
  all: ['ingestion'] as const,
  dashboard: () => [...ingestionKeys.all, 'dashboard'] as const,
}

export function useIngestionDashboard() {
  return useQuery({
    queryKey: ingestionKeys.dashboard(),
    queryFn: () => apiClient.get<IngestionDashboard>('/dashboard/ingestion'),
    staleTime: 30 * 1000,
    refetchOnWindowFocus: false,
  })
}

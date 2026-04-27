import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { WorkerStatusResponse } from '../types'

export function useWorkerStatus() {
  return useQuery({
    queryKey: ['worker-status'],
    queryFn: () => apiClient.get<WorkerStatusResponse>('/dashboard/worker-status'),
    refetchInterval: 15_000,
  })
}

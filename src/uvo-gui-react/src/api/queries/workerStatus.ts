import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import { ingestionKeys } from './ingestion'
import { INGESTION_POLL_MS } from './ingestionLog'
import type { WorkerStatusResponse } from '../types'

export function useWorkerStatus() {
  return useQuery({
    queryKey: ingestionKeys.workerStatus(),
    queryFn: ({ signal }) =>
      apiClient.get<WorkerStatusResponse>('/dashboard/worker-status', { signal }),
    refetchInterval: INGESTION_POLL_MS,
    refetchIntervalInBackground: false,
  })
}

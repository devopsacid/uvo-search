import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { GraphResponse } from '../types'

export const graphKeys = {
  all: ['graph'] as const,
  ego: (ico: string, hops: number) => [...graphKeys.all, 'ego', ico, hops] as const,
  cpv: (cpv: string, year: number) => [...graphKeys.all, 'cpv', cpv, year] as const,
}

export function useEgoGraph(ico: string, hops = 2) {
  return useQuery({
    queryKey: graphKeys.ego(ico, hops),
    queryFn: () => apiClient.get<GraphResponse>(`/graph/ego/${encodeURIComponent(ico)}?hops=${hops}`),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(ico),
  })
}

export function useCpvGraph(cpv: string, year: number) {
  return useQuery({
    queryKey: graphKeys.cpv(cpv, year),
    queryFn: () =>
      apiClient.get<GraphResponse>(
        `/graph/cpv/${encodeURIComponent(cpv)}?year=${year}`,
      ),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(cpv) && year > 0,
  })
}

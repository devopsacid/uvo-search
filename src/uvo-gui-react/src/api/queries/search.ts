import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { EntitySearchResponse } from '../types'

export const searchKeys = {
  all: ['search'] as const,
  entities: (q: string, limit?: number) => [...searchKeys.all, 'entities', q, limit] as const,
}

export function useEntityAutocomplete(query: string, limit = 10) {
  return useQuery({
    queryKey: searchKeys.entities(query, limit),
    queryFn: () => {
      const params = new URLSearchParams({ q: query, limit: String(limit) })
      return apiClient.get<EntitySearchResponse>(`/search/entities?${params.toString()}`)
    },
    enabled: query.length >= 2,
    staleTime: 30 * 1000,
  })
}

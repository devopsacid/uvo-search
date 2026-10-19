import { useQuery } from '@tanstack/react-query'
import { SEARCH_DEBOUNCE_MS, useDebouncedValue } from '@/hooks/useDebouncedValue'
import { apiClient } from '../client'
import { searchKeys } from './search'

export interface CompanyHit {
  ico: string
  name: string
  roles: string[]
  contract_count: number
}

export interface ContractHit {
  id: string
  title: string
  procurer_name: string | null
  value: number | null
  year: number | null
}

export interface UnifiedSearchResult {
  q: string
  companies: CompanyHit[]
  contracts: ContractHit[]
}

export function useUnifiedSearch(query: string) {
  const debouncedQ = useDebouncedValue(query, SEARCH_DEBOUNCE_MS)
  return useQuery({
    queryKey: searchKeys.unified(debouncedQ),
    queryFn: ({ signal }): Promise<UnifiedSearchResult> => {
      const params = new URLSearchParams({ q: debouncedQ, limit: '8' })
      return apiClient.get<UnifiedSearchResult>(`/search/unified?${params.toString()}`, {
        signal,
      })
    },
    enabled: debouncedQ.length >= 2,
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  })
}

import { useQuery } from '@tanstack/react-query'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { apiClient } from '../client'

export interface FirmaHit {
  ico: string
  name: string
  roles: string[]
  contract_count: number
}

export interface ZakazkaHit {
  id: string
  title: string
  procurer_name: string | null
  value: number | null
  year: number | null
}

export interface UnifiedSearchResult {
  q: string
  firmy: FirmaHit[]
  zakazky: ZakazkaHit[]
}

export function useUnifiedSearch(query: string) {
  const debouncedQ = useDebouncedValue(query, 250)
  return useQuery({
    queryKey: ['search', 'unified', debouncedQ],
    queryFn: (): Promise<UnifiedSearchResult> => {
      const params = new URLSearchParams({ q: debouncedQ, limit: '8' })
      return apiClient.get<UnifiedSearchResult>(`/search/unified?${params.toString()}`)
    },
    enabled: debouncedQ.length >= 2,
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  })
}

import { useQuery } from '@tanstack/react-query'

export interface FirmaStatsBlock {
  contract_count: number
  total_value: number
  last_contract_at: string | null
}

export interface FirmaStats {
  as_supplier: FirmaStatsBlock | null
  as_procurer: FirmaStatsBlock | null
}

export interface FirmaTopContract {
  id: string
  title: string
  value: number | null
  year: number | null
  counterparty_name: string | null
  counterparty_ico: string | null
  role: string
}

export interface FirmaTopCpv {
  code: string
  label: string
  contract_count: number
  total_value: number
}

export interface SpendByYear {
  year: number
  total_value: number
  contract_count: number
}

export interface FirmaProfile {
  ico: string
  name: string
  roles: string[]
  primary_role: string
  stats: FirmaStats
  top_cpvs: FirmaTopCpv[]
  top_contracts: FirmaTopContract[]
  spend_by_year: SpendByYear[]
}

export function useFirmaProfile(ico: string) {
  return useQuery({
    queryKey: ['firma', ico, 'profile'],
    queryFn: async (): Promise<FirmaProfile> => {
      const res = await fetch(`/api/firma/${ico}`)
      if (res.status === 404) throw Object.assign(new Error('not found'), { status: 404 })
      if (!res.ok) throw new Error('fetch failed')
      return res.json()
    },
    enabled: !!ico,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

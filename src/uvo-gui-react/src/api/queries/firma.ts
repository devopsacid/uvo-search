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

export interface PartnerRow {
  ico: string | null
  name: string | null
  role: string
  contract_count: number
  total_value: number
  last_contract_at: string | null
}

export interface PartnerListResponse {
  total: number
  items: PartnerRow[]
}

export function useFirmaPartneri(
  ico: string,
  params: { role: string; sort: string; limit: number; offset: number },
) {
  return useQuery({
    queryKey: ['firma', ico, 'partneri', params],
    queryFn: async (): Promise<PartnerListResponse> => {
      const sp = new URLSearchParams({
        role: params.role,
        sort: params.sort,
        limit: String(params.limit),
        offset: String(params.offset),
      })
      const res = await fetch(`/api/firma/${ico}/partneri?${sp}`)
      if (!res.ok) throw new Error('fetch failed')
      return res.json()
    },
    enabled: !!ico,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  })
}

export interface CpvProfileRow {
  code: string
  label: string
  total_value: number
  contract_count: number
  percentage: number
}

export interface CpvProfileResponse {
  for_company: CpvProfileRow[]
  market_baseline: CpvProfileRow[]
}

export function useFirmaCpvProfile(ico: string) {
  return useQuery({
    queryKey: ['firma', ico, 'cpv'],
    queryFn: async (): Promise<CpvProfileResponse> => {
      const res = await fetch(`/api/firma/${ico}/cpv-profile`)
      if (!res.ok) throw new Error('fetch failed')
      return res.json()
    },
    enabled: !!ico,
    staleTime: 5 * 60 * 1000,
  })
}

export interface FirmaCard {
  ico: string
  name: string
  roles: string[]
  contract_count: number
  total_value: number
}

export interface FirmaListResponse {
  total: number
  items: FirmaCard[]
}

export function useFirmyList(params: { q: string; role: string; limit: number; offset: number }) {
  return useQuery({
    queryKey: ['firmy', params],
    queryFn: async (): Promise<FirmaListResponse> => {
      const sp = new URLSearchParams({
        q: params.q,
        role: params.role,
        limit: String(params.limit),
        offset: String(params.offset),
      })
      const res = await fetch(`/api/firmy?${sp}`)
      if (!res.ok) throw new Error('fetch failed')
      return res.json()
    },
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  })
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

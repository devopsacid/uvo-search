import { useQuery } from '@tanstack/react-query'
import { SEARCH_DEBOUNCE_MS, useDebouncedValue } from '@/hooks/useDebouncedValue'
import { apiClient } from '../client'

export const firmaKeys = {
  all: ['firma'] as const,
  list: (params: object) => [...firmaKeys.all, 'list', params] as const,
  profile: (ico: string) => [...firmaKeys.all, 'profile', ico] as const,
  partneri: (ico: string, params: object) => [...firmaKeys.all, 'partneri', ico, params] as const,
  cpv: (ico: string) => [...firmaKeys.all, 'cpv', ico] as const,
}

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
    queryKey: firmaKeys.partneri(ico, params),
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({
        role: params.role,
        sort: params.sort,
        limit: String(params.limit),
        offset: String(params.offset),
      })
      return apiClient.get<PartnerListResponse>(`/firma/${ico}/partneri?${sp}`, { signal })
    },
    enabled: !!ico,
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
    queryKey: firmaKeys.cpv(ico),
    queryFn: ({ signal }) =>
      apiClient.get<CpvProfileResponse>(`/firma/${ico}/cpv-profile`, { signal }),
    enabled: !!ico,
    placeholderData: (prev) => prev,
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
  const debouncedQ = useDebouncedValue(params.q, SEARCH_DEBOUNCE_MS)
  return useQuery({
    queryKey: firmaKeys.list({ ...params, q: debouncedQ }),
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({
        q: debouncedQ,
        role: params.role,
        limit: String(params.limit),
        offset: String(params.offset),
      })
      return apiClient.get<FirmaListResponse>(`/firmy?${sp}`, { signal })
    },
    placeholderData: (prev) => prev,
  })
}

export function useFirmaProfile(ico: string) {
  return useQuery({
    queryKey: firmaKeys.profile(ico),
    // HttpError carries .status, so FirmaPage can tell 404 from other failures.
    queryFn: ({ signal }) => apiClient.get<FirmaProfile>(`/firma/${ico}`, { signal }),
    enabled: !!ico,
  })
}

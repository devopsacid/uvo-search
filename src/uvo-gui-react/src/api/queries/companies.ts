import { useQuery } from '@tanstack/react-query'
import { SEARCH_DEBOUNCE_MS, useDebouncedValue } from '@/hooks/useDebouncedValue'
import { apiClient } from '../client'

export const companyKeys = {
  all: ['company'] as const,
  list: (params: object) => [...companyKeys.all, 'list', params] as const,
  profile: (ico: string) => [...companyKeys.all, 'profile', ico] as const,
  partners: (ico: string, params: object) => [...companyKeys.all, 'partners', ico, params] as const,
  cpv: (ico: string) => [...companyKeys.all, 'cpv', ico] as const,
}

export interface CompanyStatsBlock {
  contract_count: number
  total_value: number
  last_contract_at: string | null
}

export interface CompanyStats {
  as_supplier: CompanyStatsBlock | null
  as_procurer: CompanyStatsBlock | null
}

export interface CompanyTopContract {
  id: string
  title: string
  value: number | null
  year: number | null
  counterparty_name: string | null
  counterparty_ico: string | null
  role: string
}

export interface CompanyTopCpv {
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

export interface CompanyProfile {
  ico: string
  name: string
  roles: string[]
  primary_role: string
  stats: CompanyStats
  top_cpvs: CompanyTopCpv[]
  top_contracts: CompanyTopContract[]
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

export function useCompanyPartners(
  ico: string,
  params: { role: string; sort: string; limit: number; offset: number },
) {
  return useQuery({
    queryKey: companyKeys.partners(ico, params),
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({
        role: params.role,
        sort: params.sort,
        limit: String(params.limit),
        offset: String(params.offset),
      })
      return apiClient.get<PartnerListResponse>(`/companies/${ico}/partners?${sp}`, { signal })
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

export function useCompanyCpvProfile(ico: string) {
  return useQuery({
    queryKey: companyKeys.cpv(ico),
    queryFn: ({ signal }) =>
      apiClient.get<CpvProfileResponse>(`/companies/${ico}/cpv-profile`, { signal }),
    enabled: !!ico,
    placeholderData: (prev) => prev,
  })
}

export interface CompanyCard {
  ico: string
  name: string
  roles: string[]
  contract_count: number
  total_value: number
}

export interface CompanyListResponse {
  total: number
  items: CompanyCard[]
}

export function useCompaniesList(params: { q: string; role: string; limit: number; offset: number }) {
  const debouncedQ = useDebouncedValue(params.q, SEARCH_DEBOUNCE_MS)
  return useQuery({
    queryKey: companyKeys.list({ ...params, q: debouncedQ }),
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({
        q: debouncedQ,
        role: params.role,
        limit: String(params.limit),
        offset: String(params.offset),
      })
      return apiClient.get<CompanyListResponse>(`/companies?${sp}`, { signal })
    },
    placeholderData: (prev) => prev,
  })
}

export function useCompanyProfile(ico: string) {
  return useQuery({
    queryKey: companyKeys.profile(ico),
    // HttpError carries .status, so CompanyPage can tell 404 from other failures.
    queryFn: ({ signal }) => apiClient.get<CompanyProfile>(`/companies/${ico}`, { signal }),
    enabled: !!ico,
  })
}

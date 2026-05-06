import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { ContractDetail, ContractListResponse } from '../types'

export interface ContractFilters {
  q?: string
  cpv?: string
  date_from?: string
  date_to?: string
  value_min?: number
  value_max?: number
  ico?: string
  supplier_ico?: string
  procurer_ico?: string
  page?: number
  page_size?: number
}

export const contractKeys = {
  all: ['contracts'] as const,
  list: (filters: ContractFilters) => [...contractKeys.all, 'list', filters] as const,
  detail: (id: string) => [...contractKeys.all, 'detail', id] as const,
}

function buildContractParams(filters: ContractFilters): string {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.cpv) params.set('cpv', filters.cpv)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.value_min != null) params.set('value_min', String(filters.value_min))
  if (filters.value_max != null) params.set('value_max', String(filters.value_max))
  if (filters.ico) params.set('ico', filters.ico)
  if (filters.supplier_ico) params.set('supplier_ico', filters.supplier_ico)
  if (filters.procurer_ico) params.set('procurer_ico', filters.procurer_ico)

  const pageSize = filters.page_size ?? 20
  const page = filters.page ?? 1
  params.set('limit', String(pageSize))
  params.set('offset', String((page - 1) * pageSize))

  return params.toString()
}

export function useContractSearch(filters: ContractFilters) {
  return useQuery({
    queryKey: contractKeys.list(filters),
    queryFn: () => {
      const qs = buildContractParams(filters)
      return apiClient.get<ContractListResponse>(`/contracts${qs ? `?${qs}` : ''}`)
    },
    staleTime: 60 * 1000,
    placeholderData: (prev) => prev,
  })
}

export function useContractDetail(id: string) {
  return useQuery({
    queryKey: contractKeys.detail(id),
    queryFn: () => apiClient.get<ContractDetail>(`/contracts/${id}`),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(id),
  })
}

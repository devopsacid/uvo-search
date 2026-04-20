import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { SupplierDetail, SupplierListResponse, SupplierSummary } from '../types'

export interface SupplierFilters {
  q?: string
  ico?: string
  page?: number
  page_size?: number
}

export const supplierKeys = {
  all: ['suppliers'] as const,
  list: (filters: SupplierFilters) => [...supplierKeys.all, 'list', filters] as const,
  detail: (ico: string) => [...supplierKeys.all, 'detail', ico] as const,
  summary: (ico: string) => [...supplierKeys.all, 'summary', ico] as const,
}

function buildSupplierParams(filters: SupplierFilters): string {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.ico) params.set('ico', filters.ico)
  const pageSize = filters.page_size ?? 20
  const page = filters.page ?? 1
  params.set('limit', String(pageSize))
  params.set('offset', String((page - 1) * pageSize))
  return params.toString()
}

export function useSuppliers(filters: SupplierFilters) {
  return useQuery({
    queryKey: supplierKeys.list(filters),
    queryFn: () => {
      const qs = buildSupplierParams(filters)
      return apiClient.get<SupplierListResponse>(`/suppliers${qs ? `?${qs}` : ''}`)
    },
    staleTime: 60 * 1000,
    placeholderData: (prev) => prev,
  })
}

export function useSupplier(ico: string) {
  return useQuery({
    queryKey: supplierKeys.detail(ico),
    queryFn: () => apiClient.get<SupplierDetail>(`/suppliers/${ico}`),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(ico),
  })
}

export function useSupplierSummary(ico: string) {
  return useQuery({
    queryKey: supplierKeys.summary(ico),
    queryFn: () => apiClient.get<SupplierSummary>(`/suppliers/${ico}/summary`),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(ico),
  })
}

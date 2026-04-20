import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { ConcentrationResponse, ProcurerDetail, ProcurerListResponse, ProcurerSummary } from '../types'

export interface ProcurerFilters {
  q?: string
  ico?: string
  page?: number
  page_size?: number
}

export const procurerKeys = {
  all: ['procurers'] as const,
  list: (filters: ProcurerFilters) => [...procurerKeys.all, 'list', filters] as const,
  detail: (ico: string) => [...procurerKeys.all, 'detail', ico] as const,
  summary: (ico: string) => [...procurerKeys.all, 'summary', ico] as const,
  concentration: (ico: string, topN: number) =>
    [...procurerKeys.all, 'concentration', ico, topN] as const,
}

function buildProcurerParams(filters: ProcurerFilters): string {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.ico) params.set('ico', filters.ico)
  const pageSize = filters.page_size ?? 20
  const page = filters.page ?? 1
  params.set('limit', String(pageSize))
  params.set('offset', String((page - 1) * pageSize))
  return params.toString()
}

export function useProcurers(filters: ProcurerFilters) {
  return useQuery({
    queryKey: procurerKeys.list(filters),
    queryFn: () => {
      const qs = buildProcurerParams(filters)
      return apiClient.get<ProcurerListResponse>(`/procurers${qs ? `?${qs}` : ''}`)
    },
    staleTime: 60 * 1000,
    placeholderData: (prev) => prev,
  })
}

export function useProcurer(ico: string) {
  return useQuery({
    queryKey: procurerKeys.detail(ico),
    queryFn: () => apiClient.get<ProcurerDetail>(`/procurers/${ico}`),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(ico),
  })
}

export function useProcurerSummary(ico: string) {
  return useQuery({
    queryKey: procurerKeys.summary(ico),
    queryFn: () => apiClient.get<ProcurerSummary>(`/procurers/${ico}/summary`),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(ico),
  })
}

export function useProcurerConcentration(ico: string, topN = 10) {
  return useQuery({
    queryKey: procurerKeys.concentration(ico, topN),
    queryFn: () =>
      apiClient.get<ConcentrationResponse>(
        `/procurers/${ico}/concentration?top_n=${topN}`,
      ),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(ico),
  })
}

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type {
  CpvShare,
  DashboardSummary,
  RecentContract,
  SpendByYear,
  TopProcurer,
  TopSupplier,
} from '../types'

export const dashboardKeys = {
  all: ['dashboard'] as const,
  summary: (ico?: string, entityType?: string) =>
    [...dashboardKeys.all, 'summary', ico, entityType] as const,
  spendByYear: (ico?: string, entityType?: string) =>
    [...dashboardKeys.all, 'spendByYear', ico, entityType] as const,
  topSuppliers: (n?: number) => [...dashboardKeys.all, 'topSuppliers', n] as const,
  topProcurers: (n?: number) => [...dashboardKeys.all, 'topProcurers', n] as const,
  cpvShare: (yearFrom?: number, yearTo?: number, ico?: string, entityType?: string) =>
    [...dashboardKeys.all, 'cpvShare', yearFrom, yearTo, ico, entityType] as const,
  recent: (limit?: number, ico?: string, entityType?: string) =>
    [...dashboardKeys.all, 'recent', limit, ico, entityType] as const,
}

export function useDashboardSummary(ico?: string, entityType?: string) {
  return useQuery({
    queryKey: dashboardKeys.summary(ico, entityType),
    queryFn: ({ signal }) => {
      const params = new URLSearchParams()
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      const qs = params.toString()
      return apiClient.get<DashboardSummary>(`/dashboard/summary${qs ? `?${qs}` : ''}`, { signal })
    },
  })
}

export function useSpendByYear(ico?: string, entityType?: string) {
  return useQuery({
    queryKey: dashboardKeys.spendByYear(ico, entityType),
    queryFn: ({ signal }) => {
      const params = new URLSearchParams()
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      const qs = params.toString()
      return apiClient.get<SpendByYear[]>(`/dashboard/spend-by-year${qs ? `?${qs}` : ''}`, { signal })
    },
  })
}

export function useTopSuppliers(n = 10) {
  return useQuery({
    queryKey: dashboardKeys.topSuppliers(n),
    queryFn: ({ signal }) => apiClient.get<TopSupplier[]>(`/dashboard/top-suppliers?n=${n}`, { signal }),
  })
}

export function useTopProcurers(n = 10) {
  return useQuery({
    queryKey: dashboardKeys.topProcurers(n),
    queryFn: ({ signal }) => apiClient.get<TopProcurer[]>(`/dashboard/top-procurers?n=${n}`, { signal }),
  })
}

export function useCpvShare(
  yearFrom?: number,
  yearTo?: number,
  ico?: string,
  entityType?: string,
) {
  return useQuery({
    queryKey: dashboardKeys.cpvShare(yearFrom, yearTo, ico, entityType),
    queryFn: ({ signal }) => {
      const params = new URLSearchParams()
      if (yearFrom != null) params.set('year_from', String(yearFrom))
      if (yearTo != null) params.set('year_to', String(yearTo))
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      const qs = params.toString()
      return apiClient.get<CpvShare[]>(`/dashboard/by-cpv${qs ? `?${qs}` : ''}`, { signal })
    },
  })
}

export function useRecent(limit = 10, ico?: string, entityType?: string) {
  return useQuery({
    queryKey: dashboardKeys.recent(limit, ico, entityType),
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({ limit: String(limit) })
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      return apiClient.get<RecentContract[]>(`/dashboard/recent?${params.toString()}`, { signal })
    },
    staleTime: 60 * 1000,
  })
}

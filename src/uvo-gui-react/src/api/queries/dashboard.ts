import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type {
  CpvShare,
  DashboardSummary,
  MonthBucket,
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
  cpvShare: (yearFrom?: number, yearTo?: number) =>
    [...dashboardKeys.all, 'cpvShare', yearFrom, yearTo] as const,
  recent: (limit?: number) => [...dashboardKeys.all, 'recent', limit] as const,
  byMonth: (year: number) => [...dashboardKeys.all, 'byMonth', year] as const,
}

export function useDashboardSummary(ico?: string, entityType?: string) {
  return useQuery({
    queryKey: dashboardKeys.summary(ico, entityType),
    queryFn: () => {
      const params = new URLSearchParams()
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      const qs = params.toString()
      return apiClient.get<DashboardSummary>(`/dashboard/summary${qs ? `?${qs}` : ''}`)
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useSpendByYear(ico?: string, entityType?: string) {
  return useQuery({
    queryKey: dashboardKeys.spendByYear(ico, entityType),
    queryFn: () => {
      const params = new URLSearchParams()
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      const qs = params.toString()
      return apiClient.get<SpendByYear[]>(`/dashboard/spend-by-year${qs ? `?${qs}` : ''}`)
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useTopSuppliers(n = 10) {
  return useQuery({
    queryKey: dashboardKeys.topSuppliers(n),
    queryFn: () => apiClient.get<TopSupplier[]>(`/dashboard/top-suppliers?n=${n}`),
    staleTime: 5 * 60 * 1000,
  })
}

export function useTopProcurers(n = 10) {
  return useQuery({
    queryKey: dashboardKeys.topProcurers(n),
    queryFn: () => apiClient.get<TopProcurer[]>(`/dashboard/top-procurers?n=${n}`),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCpvShare(yearFrom?: number, yearTo?: number) {
  return useQuery({
    queryKey: dashboardKeys.cpvShare(yearFrom, yearTo),
    queryFn: () => {
      const params = new URLSearchParams()
      if (yearFrom != null) params.set('year_from', String(yearFrom))
      if (yearTo != null) params.set('year_to', String(yearTo))
      const qs = params.toString()
      return apiClient.get<CpvShare[]>(`/dashboard/by-cpv${qs ? `?${qs}` : ''}`)
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useRecent(limit = 10) {
  return useQuery({
    queryKey: dashboardKeys.recent(limit),
    queryFn: () => apiClient.get<RecentContract[]>(`/dashboard/recent?limit=${limit}`),
    staleTime: 60 * 1000,
  })
}

export function useByMonth(year: number) {
  return useQuery({
    queryKey: dashboardKeys.byMonth(year),
    queryFn: () => apiClient.get<MonthBucket[]>(`/dashboard/by-month?year=${year}`),
    staleTime: 5 * 60 * 1000,
    enabled: year > 0,
  })
}

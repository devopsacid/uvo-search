import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { ExecutiveSummary, PeriodSummary } from '../types'

const STALE = 5 * 60 * 1000

export const analyticsKeys = {
  all: ['analytics'] as const,
  procurerPeriod: (ico: string, dateFrom: string, dateTo: string) =>
    [...analyticsKeys.all, 'procurer', ico, dateFrom, dateTo] as const,
  supplierPeriod: (ico: string, dateFrom: string, dateTo: string) =>
    [...analyticsKeys.all, 'supplier', ico, dateFrom, dateTo] as const,
  executive: (ico: string, dateFrom: string, dateTo: string, entityType: string) =>
    [...analyticsKeys.all, 'executive', ico, dateFrom, dateTo, entityType] as const,
}

function periodParams(dateFrom: string, dateTo: string): string {
  return `date_from=${dateFrom}&date_to=${dateTo}`
}

export function useProcurerPeriodSummary(ico: string, dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: analyticsKeys.procurerPeriod(ico, dateFrom, dateTo),
    queryFn: () =>
      apiClient.get<PeriodSummary>(
        `/procurers/${ico}/period-summary?${periodParams(dateFrom, dateTo)}`,
      ),
    staleTime: STALE,
    enabled: Boolean(ico && dateFrom && dateTo),
  })
}

export function useSupplierPeriodSummary(ico: string, dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: analyticsKeys.supplierPeriod(ico, dateFrom, dateTo),
    queryFn: () =>
      apiClient.get<PeriodSummary>(
        `/suppliers/${ico}/period-summary?${periodParams(dateFrom, dateTo)}`,
      ),
    staleTime: STALE,
    enabled: Boolean(ico && dateFrom && dateTo),
  })
}

export function useExecutiveSummary(
  ico: string,
  dateFrom: string,
  dateTo: string,
  entityType: 'procurer' | 'supplier',
) {
  return useQuery({
    queryKey: analyticsKeys.executive(ico, dateFrom, dateTo, entityType),
    queryFn: () =>
      apiClient.get<ExecutiveSummary>(
        `/companies/${ico}/executive-summary?${periodParams(dateFrom, dateTo)}&entity_type=${entityType}`,
      ),
    staleTime: STALE,
    enabled: Boolean(ico && dateFrom && dateTo),
  })
}

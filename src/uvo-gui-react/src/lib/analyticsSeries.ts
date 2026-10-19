import type { TimeseriesSeries } from '@/api/types'
import { formatPeriodLabel } from '@/lib/analyticsFilters'

/** Pivot series -> one row per period with a column per series key. */
export function pivotSeries(
  series: TimeseriesSeries[],
  metric: 'total_value' | 'contract_count' = 'total_value',
): Record<string, string | number>[] {
  const rows = new Map<string, Record<string, string | number>>()
  for (const s of series) {
    for (const p of s.points) {
      const row = rows.get(p.period) ?? { period: p.period, label: formatPeriodLabel(p.period) }
      row[s.key] = p[metric]
      rows.set(p.period, row)
    }
  }
  return [...rows.values()].sort((a, b) => String(a.period).localeCompare(String(b.period)))
}

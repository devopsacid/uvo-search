import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useCpvShare } from '@/api/queries/dashboard'
import { Skeleton } from '@/components/ui/Skeleton'
import { StackedAreaChart, type AreaSeries } from '@/components/charts/StackedAreaChart'
import { formatCurrency } from '@/lib/utils'
import sk from '@/i18n/sk'

const CURRENT_YEAR = new Date().getFullYear()

const COLORS = [
  '#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed',
  '#db2777', '#0891b2', '#65a30d', '#9f1239', '#1d4ed8',
]

export function CpvTrendsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const yearFrom = searchParams.get('year_from') ? Number(searchParams.get('year_from')) : CURRENT_YEAR - 4
  const yearTo = searchParams.get('year_to') ? Number(searchParams.get('year_to')) : CURRENT_YEAR

  const [fromInput, setFromInput] = useState(String(yearFrom))
  const [toInput, setToInput] = useState(String(yearTo))

  const { data, isLoading } = useCpvShare(yearFrom, yearTo)

  function applyFilters() {
    const f = parseInt(fromInput)
    const t = parseInt(toInput)
    if (!isNaN(f) && !isNaN(t)) {
      setSearchParams({ year_from: String(f), year_to: String(t) })
    }
  }

  // Transform flat CpvShare list into chart data keyed by year (we don't have per-year breakdown
  // from the current endpoint — we show the aggregated view as a bar by CPV code instead)
  // We use a horizontal bar chart to show CPV distribution for the selected range.
  const top10 = (data ?? []).slice(0, 10)

  function handleCpvClick(cpvCode: string) {
    navigate(`/search?cpv=${encodeURIComponent(cpvCode)}`)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">{sk.cpvTrends.title}</h1>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-4 rounded-lg border border-border bg-card p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">{sk.cpvTrends.yearFrom}</label>
          <input
            type="number"
            value={fromInput}
            onChange={(e) => setFromInput(e.target.value)}
            className="w-24 rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            min={2010}
            max={CURRENT_YEAR}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">{sk.cpvTrends.yearTo}</label>
          <input
            type="number"
            value={toInput}
            onChange={(e) => setToInput(e.target.value)}
            className="w-24 rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            min={2010}
            max={CURRENT_YEAR}
          />
        </div>
        <button
          onClick={applyFilters}
          className="rounded bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          {sk.cpvTrends.apply}
        </button>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : top10.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">{sk.cpvTrends.noData}</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">{sk.cpvTrends.drillHint}</p>

          {/* CPV share table with colored bars */}
          <div className="rounded-lg border border-border bg-card">
            {top10.map((item, i) => (
              <button
                key={item.cpv_code}
                onClick={() => handleCpvClick(item.cpv_code)}
                className="group flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left last:border-0 hover:bg-accent"
              >
                <div
                  className="h-3 w-3 flex-shrink-0 rounded-sm"
                  style={{ backgroundColor: COLORS[i % COLORS.length] }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm font-medium text-foreground group-hover:text-primary">
                      {item.label_sk}
                    </span>
                    <span className="flex-shrink-0 text-xs text-muted-foreground">
                      {item.percentage}%
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${item.percentage}%`,
                          backgroundColor: COLORS[i % COLORS.length],
                        }}
                      />
                    </div>
                    <span className="flex-shrink-0 text-xs text-muted-foreground">
                      {formatCurrency(item.total_value)}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

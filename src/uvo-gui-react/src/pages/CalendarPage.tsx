import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useByMonth } from '@/api/queries/dashboard'
import { CalendarHeatmap } from '@/components/charts/CalendarHeatmap'
import sk from '@/i18n/sk'

const CURRENT_YEAR = new Date().getFullYear()

export function CalendarPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const yearParam = searchParams.get('year')
  const [year, setYear] = useState(yearParam ? Number(yearParam) : CURRENT_YEAR)

  const { data, isLoading } = useByMonth(year)

  function handleCellClick(month: number) {
    navigate(`/search?year=${year}&month=${month}`)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{sk.calendar.title}</h1>
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">{sk.calendar.yearLabel}:</label>
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            min={2010}
            max={CURRENT_YEAR}
            className="w-24 rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : !data || data.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">{sk.calendar.noData}</p>
        </div>
      ) : (
        <CalendarHeatmap
          data={data}
          monthNames={[...sk.calendar.monthNames]}
          onCellClick={handleCellClick}
        />
      )}
    </div>
  )
}

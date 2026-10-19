import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TimeseriesPoint } from '@/api/types'
import { CHART_COLORS } from '@/components/analytics/palette'
import { formatPeriodLabel } from '@/lib/analyticsFilters'
import { formatCompactCurrency, formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

interface TimeseriesChartProps {
  points: TimeseriesPoint[]
  /** Bar click -> drill-down for that bucket. */
  onSelectPeriod?: (period: string) => void
  height?: number
}

/** Bars = value (left axis), line = contract count (right axis). */
export function TimeseriesChart({ points, onSelectPeriod, height = 288 }: TimeseriesChartProps) {
  const data = points.map((p) => ({ ...p, label: formatPeriodLabel(p.period) }))
  const dense = data.length > 18

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={dense ? 'preserveStartEnd' : 0} minTickGap={12} />
        <YAxis
          yAxisId="value"
          tickFormatter={formatCompactCurrency}
          tick={{ fontSize: 11 }}
          width={72}
        />
        <YAxis
          yAxisId="count"
          orientation="right"
          tickFormatter={(v: number) => formatNumber(v)}
          tick={{ fontSize: 11 }}
          width={48}
        />
        <Tooltip
          formatter={(value: number, name: string) =>
            name === sk.analytics.prehlad.valueSeries ? [formatCurrency(value), name] : [formatNumber(value), name]
          }
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
        />
        <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
        <Bar
          yAxisId="value"
          dataKey="total_value"
          name={sk.analytics.prehlad.valueSeries}
          fill={CHART_COLORS[0]}
          radius={[3, 3, 0, 0]}
          cursor={onSelectPeriod ? 'pointer' : undefined}
          onClick={(d: { period?: string }) => {
            if (d.period && onSelectPeriod) onSelectPeriod(d.period)
          }}
          isAnimationActive={false}
        />
        <Line
          yAxisId="count"
          dataKey="contract_count"
          name={sk.analytics.prehlad.countSeries}
          stroke={CHART_COLORS[1]}
          strokeWidth={2}
          dot={!dense}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

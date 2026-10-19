import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TimeseriesSeries } from '@/api/types'
import { seriesColor } from '@/components/analytics/palette'
import { pivotSeries } from '@/lib/analyticsSeries'
import { formatCompactCurrency, formatCurrency, formatNumber } from '@/lib/utils'

interface StackedPeriodChartProps {
  series: TimeseriesSeries[]
  /** Which point field is stacked: value (EUR) or number of contracts/notices. */
  metric?: 'total_value' | 'contract_count'
  height?: number
}

/** Stacked bars per period, one stack segment per series (value). */
export function StackedPeriodChart({ series, metric = 'total_value', height = 288 }: StackedPeriodChartProps) {
  const data = pivotSeries(series, metric)
  const money = metric === 'total_value'
  const labels = new Map(series.map((s) => [s.key, s.label]))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={12} />
        <YAxis tickFormatter={money ? formatCompactCurrency : (v: number) => formatNumber(v)} tick={{ fontSize: 11 }} width={72} />
        <Tooltip
          formatter={(value: number, key: string) => [money ? formatCurrency(value) : formatNumber(value), labels.get(key) ?? key]}
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
        />
        <Legend
          verticalAlign="top"
          height={36}
          wrapperStyle={{ fontSize: 12 }}
          formatter={(key: string) => labels.get(key) ?? key}
        />
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            stackId="period"
            fill={seriesColor(i, s.key)}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

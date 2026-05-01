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
import type { MonthlySpendBucket } from '@/api/types'
import { formatCurrency } from '@/lib/utils'

interface MonthlySpendChartProps {
  data: MonthlySpendBucket[]
  height?: number
}

function fmtMonth(month: string): string {
  // YYYY-MM → MM/YY
  const [y, m] = month.split('-')
  return `${m}/${y.slice(2)}`
}

function fmtAxis(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} tis.`
  return String(value)
}

export function MonthlySpendChart({ data, height = 240 }: MonthlySpendChartProps) {
  if (!data.length) return null

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 4, right: 12, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="month"
          tickFormatter={fmtMonth}
          tick={{ fontSize: 11 }}
          interval="preserveStartEnd"
        />
        <YAxis
          yAxisId="value"
          orientation="left"
          tickFormatter={fmtAxis}
          tick={{ fontSize: 11 }}
          width={62}
        />
        <YAxis
          yAxisId="count"
          orientation="right"
          tick={{ fontSize: 11 }}
          width={36}
          allowDecimals={false}
        />
        <Tooltip
          formatter={(value: number, name: string) =>
            name === 'total_value'
              ? [formatCurrency(value), 'Objem']
              : [value, 'Zmluvy']
          }
          labelFormatter={fmtMonth}
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
        />
        <Legend
          iconSize={10}
          wrapperStyle={{ fontSize: 12 }}
          formatter={(name) => (name === 'total_value' ? 'Objem' : 'Zmluvy')}
        />
        <Bar
          yAxisId="value"
          dataKey="total_value"
          fill="hsl(var(--primary))"
          opacity={0.85}
          radius={[2, 2, 0, 0]}
        />
        <Line
          yAxisId="count"
          dataKey="contract_count"
          stroke="hsl(var(--muted-foreground))"
          strokeWidth={1.5}
          dot={false}
          type="monotone"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

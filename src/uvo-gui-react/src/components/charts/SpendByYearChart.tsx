import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { SpendByYear } from '@/api/types'
import { formatCurrency } from '@/lib/utils'

interface SpendByYearChartProps {
  data: SpendByYear[]
}

function formatMillions(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} M €`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} tis. €`
  return `${value} €`
}

export function SpendByYearChart({ data }: SpendByYearChartProps) {
  if (!data.length) return null

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="year"
          tick={{ fontSize: 12 }}
          className="fill-muted-foreground"
        />
        <YAxis
          tickFormatter={formatMillions}
          tick={{ fontSize: 11 }}
          width={70}
          className="fill-muted-foreground"
        />
        <Tooltip
          formatter={(value: number) => [formatCurrency(value), 'Objem']}
          labelFormatter={(label) => `Rok ${label}`}
          contentStyle={{
            fontSize: 12,
            borderRadius: 6,
          }}
        />
        <Bar dataKey="total_value" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

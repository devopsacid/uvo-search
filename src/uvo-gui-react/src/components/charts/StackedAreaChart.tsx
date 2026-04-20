import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatCurrency } from '@/lib/utils'

export interface AreaSeries {
  key: string
  label: string
  color?: string
}

interface StackedAreaChartProps {
  data: Record<string, number | string>[]
  series: AreaSeries[]
  xDataKey?: string
  height?: number
}

const DEFAULT_COLORS = [
  '#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed',
  '#db2777', '#0891b2', '#65a30d',
]

function formatMillions(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)} tis.`
  return String(v)
}

export function StackedAreaChart({
  data,
  series,
  xDataKey = 'year',
  height = 280,
}: StackedAreaChartProps) {
  if (!data.length) return null

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey={xDataKey} tick={{ fontSize: 12 }} />
        <YAxis tickFormatter={formatMillions} tick={{ fontSize: 11 }} width={70} />
        <Tooltip formatter={(v: number) => [formatCurrency(v), '']} />
        <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stackId="1"
            fill={s.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length]}
            stroke={s.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length]}
            fillOpacity={0.7}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

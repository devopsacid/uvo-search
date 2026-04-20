import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

export interface DonutSlice {
  name: string
  value: number
  id?: string
}

interface DonutChartProps {
  data: DonutSlice[]
  height?: number
  valueFormatter?: (v: number) => string
}

const COLORS = [
  '#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed',
  '#db2777', '#0891b2', '#65a30d', '#9f1239', '#1d4ed8',
]

export function DonutChart({ data, height = 260, valueFormatter }: DonutChartProps) {
  if (!data.length) return null

  const fmt = valueFormatter ?? ((v: number) => v.toFixed(1))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius="55%"
          outerRadius="75%"
          dataKey="value"
          nameKey="name"
          paddingAngle={2}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(v: number) => [fmt(v), '']} />
        <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

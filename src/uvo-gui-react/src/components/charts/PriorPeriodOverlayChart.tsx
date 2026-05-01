import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MonthlySpendBucket } from '@/api/types'
import { formatCurrency } from '@/lib/utils'
import sk from '@/i18n/sk'

interface PriorPeriodOverlayChartProps {
  current: MonthlySpendBucket[]
  prior: MonthlySpendBucket[]
  height?: number
}

interface MergedRow {
  idx: number
  current: number | null
  prior: number | null
}

function fmtAxis(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} tis.`
  return String(value)
}

export function PriorPeriodOverlayChart({
  current,
  prior,
  height = 220,
}: PriorPeriodOverlayChartProps) {
  const len = Math.max(current.length, prior.length)
  if (len === 0) return null

  const merged: MergedRow[] = Array.from({ length: len }, (_, i) => ({
    idx: i + 1,
    current: current[i]?.total_value ?? null,
    prior: prior[i]?.total_value ?? null,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={merged} margin={{ top: 4, right: 12, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="idx" tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={fmtAxis} tick={{ fontSize: 11 }} width={62} />
        <Tooltip
          formatter={(value: number, name: string) => [
            formatCurrency(value),
            name === 'current'
              ? sk.analytics.executive.currentPeriod
              : sk.analytics.executive.priorPeriod,
          ]}
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
        />
        <Legend
          iconSize={10}
          wrapperStyle={{ fontSize: 12 }}
          formatter={(name) =>
            name === 'current'
              ? sk.analytics.executive.currentPeriod
              : sk.analytics.executive.priorPeriod
          }
        />
        <Line
          dataKey="current"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          dot={false}
          type="monotone"
          connectNulls
        />
        <Line
          dataKey="prior"
          stroke="hsl(var(--muted-foreground))"
          strokeWidth={1.5}
          strokeDasharray="5 3"
          dot={false}
          type="monotone"
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

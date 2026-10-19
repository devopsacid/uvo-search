import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CHART_COLORS } from '@/components/analytics/palette'
import { formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

export interface HhiPoint {
  year: number
  hhi: number | null
}

interface HhiTrendChartProps {
  points: HhiPoint[]
  height?: number
}

/** HHI per year with the orientation thresholds (1 500 / 2 500) as reference lines. */
export function HhiTrendChart({ points, height = 260 }: HhiTrendChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis dataKey="year" tick={{ fontSize: 11 }} />
        <YAxis domain={[0, 10000]} tickFormatter={(v: number) => formatNumber(v)} tick={{ fontSize: 11 }} width={56} />
        <ReferenceLine y={1500} stroke="#64748b" strokeDasharray="4 4" label={{ value: '1 500', fontSize: 10, position: 'insideBottomRight' }} />
        <ReferenceLine y={2500} stroke="#64748b" strokeDasharray="4 4" label={{ value: '2 500', fontSize: 10, position: 'insideTopRight' }} />
        <Tooltip
          formatter={(v: number) => [formatNumber(Math.round(v)), sk.analytics.concentration.hhiShort]}
          labelFormatter={(y) => `${sk.common.year} ${y}`}
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
        />
        <Line
          dataKey="hhi"
          stroke={CHART_COLORS[0]}
          strokeWidth={2}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

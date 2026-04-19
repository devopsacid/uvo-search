<script setup lang="ts">
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip } from 'chart.js'
import type { SpendByYear } from '../api/client'
import { useThemeStore } from '../stores/theme'
import { applyChartDefaults, CHART_COLORS, themedChartColors } from './charts/chartDefaults'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)
applyChartDefaults()

const props = defineProps<{ data: SpendByYear[] }>()
const theme = useThemeStore()

const chartData = computed(() => {
  // touch theme.mode so recomputes on toggle
  void theme.mode
  return {
    labels: props.data.map(d => String(d.year)),
    datasets: [{
      label: 'EUR',
      data: props.data.map(d => d.total_value),
      backgroundColor: props.data.map((_, i) =>
        i === props.data.length - 1 ? CHART_COLORS.primary : CHART_COLORS.primaryDim
      ),
      hoverBackgroundColor: CHART_COLORS.primary2,
      borderWidth: 0,
      borderRadius: 2,
      maxBarThickness: 40,
    }],
  }
})

const options = computed(() => {
  const c = themedChartColors()
  return {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        grid: { display: false },
        border: { color: c.grid },
        ticks: { color: c.ticks },
      },
      y: {
        grid: { color: c.grid, drawTicks: false },
        border: { display: false },
        ticks: {
          color: c.ticks,
          callback: (v: string | number) => {
            const n = Number(v)
            if (n >= 1_000_000_000) return `€${(n / 1_000_000_000).toFixed(1)}B`
            if (n >= 1_000_000) return `€${(n / 1_000_000).toFixed(0)}M`
            if (n >= 1_000) return `€${(n / 1_000).toFixed(0)}K`
            return `€${n}`
          },
        },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: c.tooltipBg,
        titleColor: c.tooltipFg,
        bodyColor: c.tooltipFg,
        borderColor: c.tooltipBr,
        callbacks: {
          label: (ctx: any) => {
            const n = Number(ctx.parsed.y)
            if (n >= 1_000_000) return `€${(n / 1_000_000).toFixed(2)}M`
            return `€${n.toLocaleString()}`
          },
        },
      },
    },
  }
})
</script>

<template>
  <div class="h-44">
    <Bar :data="chartData" :options="options" />
  </div>
</template>

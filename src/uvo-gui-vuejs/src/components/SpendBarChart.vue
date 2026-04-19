<script setup lang="ts">
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip } from 'chart.js'
import type { SpendByYear } from '../api/client'
import { applyTerminalChartDefaults, TERM } from './charts/chartDefaults'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)
applyTerminalChartDefaults()

const props = defineProps<{ data: SpendByYear[] }>()

const chartData = computed(() => ({
  labels: props.data.map(d => String(d.year)),
  datasets: [{
    label: '€M',
    data: props.data.map(d => d.total_value / 1_000_000),
    backgroundColor: props.data.map((_, i) =>
      i === props.data.length - 1 ? TERM.accent : TERM.accentDim
    ),
    borderWidth: 0,
    borderRadius: 0,
    barPercentage: 0.85,
    categoryPercentage: 0.85,
  }],
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    x: {
      grid: { display: false, color: TERM.grid },
      border: { display: false },
      ticks: { color: TERM.ticks, font: { size: 9 } },
    },
    y: {
      grid: { color: TERM.grid, drawTicks: false },
      border: { display: false },
      ticks: { color: TERM.ticks, font: { size: 9 }, callback: (v: string | number) => `${v}M` },
    },
  },
  plugins: { legend: { display: false } },
}
</script>

<template>
  <div class="h-36">
    <Bar :data="chartData" :options="options" />
  </div>
</template>

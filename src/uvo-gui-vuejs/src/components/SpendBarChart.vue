<script setup lang="ts">
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend } from 'chart.js'
import { useThemeStore } from '../stores/theme'
import type { SpendByYear } from '../api/client'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const props = defineProps<{ data: SpendByYear[] }>()
const theme = useThemeStore()

const chartData = computed(() => ({
  labels: props.data.map(d => String(d.year)),
  datasets: [{
    label: '€M',
    data: props.data.map(d => d.total_value / 1_000_000),
    backgroundColor: props.data.map((_, i) =>
      i === props.data.length - 1
        ? (theme.isDark ? '#38bdf8' : '#2563eb')
        : (theme.isDark ? '#1e3a5f' : '#bfdbfe')
    ),
    borderRadius: 3,
  }],
}))

const options = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false }, ticks: { color: theme.isDark ? '#94a3b8' : '#64748b' } },
    y: { grid: { color: theme.isDark ? '#1e293b' : '#f1f5f9' }, ticks: { color: theme.isDark ? '#94a3b8' : '#64748b' } },
  },
}))
</script>

<template>
  <div class="h-32">
    <Bar :data="chartData" :options="options" />
  </div>
</template>

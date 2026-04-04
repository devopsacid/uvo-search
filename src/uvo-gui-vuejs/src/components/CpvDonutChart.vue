<script setup lang="ts">
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import { useI18n } from 'vue-i18n'
import type { CpvShare } from '../api/client'

ChartJS.register(ArcElement, Tooltip, Legend)

const props = defineProps<{ data: CpvShare[] }>()
const { locale } = useI18n()

const COLORS = ['#2563eb', '#16a34a', '#dc2626', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16']

const chartData = computed(() => ({
  labels: props.data.map(d => locale.value === 'sk' ? d.label_sk : d.label_en),
  datasets: [{
    data: props.data.map(d => d.percentage),
    backgroundColor: COLORS.slice(0, props.data.length),
    borderWidth: 0,
  }],
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  cutout: '65%',
}
</script>

<template>
  <div class="flex items-center gap-4">
    <div class="w-24 h-24 flex-shrink-0">
      <Doughnut :data="chartData" :options="options" />
    </div>
    <div class="flex flex-col gap-1.5 overflow-hidden">
      <div v-for="(item, i) in data.slice(0, 5)" :key="item.cpv_code" class="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
        <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: COLORS[i] }" />
        <span class="truncate">{{ locale === 'sk' ? item.label_sk : item.label_en }}</span>
        <span class="ml-auto text-slate-500">{{ item.percentage }}%</span>
      </div>
    </div>
  </div>
</template>

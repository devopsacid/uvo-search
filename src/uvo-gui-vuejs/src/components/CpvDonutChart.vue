<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { CpvShare } from '../api/client'
import { fmtValue } from '../lib/format'
import { CHART_COLORS } from './charts/chartDefaults'

const props = defineProps<{ data: CpvShare[]; limit?: number }>()
const { locale } = useI18n()

const top = computed(() => props.data.slice(0, props.limit ?? 6))
const maxPct = computed(() => Math.max(...top.value.map(d => d.percentage), 1))
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <div
      v-for="(item, i) in top"
      :key="item.cpv_code"
      class="grid items-center gap-3 text-xs"
      style="grid-template-columns: 70px 1fr 90px 100px 50px"
    >
      <span class="dim mono">{{ item.cpv_code }}</span>
      <span class="truncate muted">
        {{ locale === 'sk' ? item.label_sk : item.label_en }}
      </span>
      <span class="relative h-[6px] bg-l-panel-2 dark:bg-d-panel-2 rounded-sm overflow-hidden">
        <span
          class="absolute inset-y-0 left-0 rounded-sm"
          :style="{ width: `${(item.percentage / maxPct) * 100}%`, background: CHART_COLORS.series[i % CHART_COLORS.series.length] }"
        />
      </span>
      <span class="text-right font-semibold num">{{ item.total_value > 0 ? fmtValue(item.total_value) : '—' }}</span>
      <span class="text-right dim num">{{ item.percentage.toFixed(1) }}%</span>
    </div>
    <div v-if="top.length === 0" class="text-xs dim py-6 text-center">—</div>
  </div>
</template>

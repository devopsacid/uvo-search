<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { CpvShare } from '../api/client'
import { fmtValue } from '../lib/format'

const props = defineProps<{ data: CpvShare[] }>()
const { locale } = useI18n()

const top = computed(() => props.data.slice(0, 6))

const maxPct = computed(() => Math.max(...top.value.map(d => d.percentage), 1))
</script>

<template>
  <div class="flex flex-col gap-1">
    <div
      v-for="(item, i) in top"
      :key="item.cpv_code"
      class="flex items-center gap-2 text-xs"
    >
      <span class="w-8 text-fg-dim num">{{ String(i + 1).padStart(2, '0') }}</span>
      <span class="flex-1 truncate text-fg-muted">
        {{ locale === 'sk' ? item.label_sk : item.label_en }}
      </span>
      <span class="w-20 h-[4px] bg-ink-700 relative">
        <span class="absolute inset-y-0 left-0 bg-accent" :style="{ width: `${(item.percentage / maxPct) * 100}%` }" />
      </span>
      <span class="w-16 text-right text-fg-primary num">{{ fmtValue(item.total_value) }}</span>
      <span class="w-10 text-right text-fg-dim num">{{ item.percentage.toFixed(1) }}%</span>
    </div>
    <div v-if="top.length === 0" class="text-fg-dim text-xs py-4 text-center">—</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { DashboardSummary } from '../api/client'
import { fmtValue } from '../lib/format'

const filter = useFilterStore()
const summary = ref<DashboardSummary | null>(null)
const now = ref(new Date())

async function load() {
  try {
    summary.value = await api.dashboard.summary(filter.queryParams)
    now.value = new Date()
  } catch {
    /* keep previous */
  }
}

onMounted(load)
watch(() => filter.queryParams, load)

function delta(key: 'total_value' | 'contract_count' | 'avg_value' | 'active_suppliers'): { text: string; dir: 'up' | 'down' | 'flat' } {
  const d = summary.value?.deltas?.[key]
  if (!d) return { text: '', dir: 'flat' }
  const pct = d.pct
  if (pct == null) return { text: '', dir: 'flat' }
  const sign = pct > 0 ? '+' : ''
  return { text: `${sign}${pct.toFixed(1)}%`, dir: pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat' }
}

function ts(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<template>
  <div class="flex items-center gap-6 px-4 py-2 bg-ink-800 border-b border-ink-600 text-xs whitespace-nowrap overflow-x-auto">
    <span class="text-accent font-bold tracking-wider">ÚVO//TERMINAL</span>

    <span class="text-fg-dim">
      VAL <b class="text-fg-primary num">{{ summary ? fmtValue(summary.total_value) : '—' }}</b>
      <span
        v-if="delta('total_value').text"
        class="ml-1 num"
        :class="{ 'text-up': delta('total_value').dir === 'up', 'text-down': delta('total_value').dir === 'down' }"
      >{{ delta('total_value').text }}</span>
    </span>

    <span class="text-fg-dim">
      CNT <b class="text-fg-primary num">{{ summary ? summary.contract_count.toLocaleString() : '—' }}</b>
    </span>

    <span class="text-fg-dim">
      AVG <b class="text-fg-primary num">{{ summary ? fmtValue(summary.avg_value) : '—' }}</b>
      <span
        v-if="delta('avg_value').text"
        class="ml-1 num"
        :class="{ 'text-up': delta('avg_value').dir === 'up', 'text-down': delta('avg_value').dir === 'down' }"
      >{{ delta('avg_value').text }}</span>
    </span>

    <span class="text-fg-dim">
      SUP <b class="text-fg-primary num">{{ summary ? summary.active_suppliers.toLocaleString() : '—' }}</b>
    </span>

    <span v-if="filter.isFiltered" class="text-accent flex items-center gap-1 ml-2">
      ▸ {{ filter.name }}
      <button @click="filter.clear()" class="ml-1 text-fg-muted hover:text-accent" title="Clear filter">✕</button>
    </span>

    <span class="ml-auto text-fg-dim num">{{ ts(now) }} SK</span>
  </div>
</template>

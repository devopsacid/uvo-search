<!-- src/uvo-gui-vuejs/src/pages/CostAnalysisPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { CpvShare, ContractRow } from '../api/client'

const { t, locale } = useI18n()
const filter = useFilterStore()

const byCpv = ref<CpvShare[]>([])
const topContracts = ref<ContractRow[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v}`
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const p = filter.queryParams
    const [cpv, contracts] = await Promise.all([
      api.dashboard.byCpv(p),
      api.contracts.list({ ...p, limit: 20 }),
    ])
    byCpv.value = cpv
    topContracts.value = [...contracts.data].sort((a, b) => b.value - a.value)
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('costs.title') }}</h1>
    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm">{{ error }}</div>
    <template v-else>
      <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm mb-4">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('costs.byCpv') }}</p>
        <div class="space-y-2">
          <div v-for="item in byCpv" :key="item.cpv_code" class="flex items-center gap-3 text-sm">
            <span class="w-40 truncate text-xs text-slate-600 dark:text-slate-400">{{ locale === 'sk' ? item.label_sk : item.label_en }}</span>
            <div class="flex-1 h-4 bg-slate-100 dark:bg-slate-700 rounded">
              <div class="h-4 bg-blue-500 dark:bg-sky-500 rounded" :style="{ width: `${item.percentage}%` }" />
            </div>
            <span class="w-24 text-right text-xs font-mono text-slate-700 dark:text-slate-300">{{ fmt(item.total_value) }}</span>
            <span class="w-10 text-right text-xs text-slate-400">{{ item.percentage }}%</span>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('costs.topContracts') }}</p>
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-slate-100 dark:border-slate-700">
              <th class="text-left text-xs uppercase text-slate-400 pb-2 pr-4">Zákazka</th>
              <th class="text-left text-xs uppercase text-slate-400 pb-2 pr-4">Obstarávateľ</th>
              <th class="text-right text-xs uppercase text-slate-400 pb-2">Hodnota</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in topContracts" :key="c.id" class="border-b border-slate-50 dark:border-slate-800">
              <td class="py-2 pr-4 text-slate-700 dark:text-slate-300 truncate max-w-xs">{{ c.title }}</td>
              <td class="py-2 pr-4 text-xs text-slate-500">{{ c.procurer_name }}</td>
              <td class="py-2 text-right font-bold text-blue-600 dark:text-sky-400 font-mono text-xs">{{ fmt(c.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

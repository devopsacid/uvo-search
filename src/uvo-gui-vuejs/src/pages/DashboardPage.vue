<!-- src/uvo-gui-vuejs/src/pages/DashboardPage.vue -->
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { DashboardSummary, SpendByYear, TopSupplier, TopProcurer, CpvShare, RecentContract } from '../api/client'
import KpiCard from '../components/KpiCard.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import CpvDonutChart from '../components/CpvDonutChart.vue'
import TopRankingList from '../components/TopRankingList.vue'

const { t } = useI18n()
const filter = useFilterStore()

const loading = ref(false)
const error = ref<string | null>(null)
const summary = ref<DashboardSummary | null>(null)
const spendByYear = ref<SpendByYear[]>([])
const topSuppliers = ref<TopSupplier[]>([])
const topProcurers = ref<TopProcurer[]>([])
const byCpv = ref<CpvShare[]>([])
const recent = ref<RecentContract[]>([])

async function load() {
  loading.value = true
  error.value = null
  try {
    const p = filter.queryParams
    const [s, sy, ts, tp, cpv, r] = await Promise.all([
      api.dashboard.summary(p),
      api.dashboard.spendByYear(p),
      api.dashboard.topSuppliers(p),
      api.dashboard.topProcurers(p),
      api.dashboard.byCpv(p),
      api.dashboard.recent(p),
    ])
    summary.value = s
    spendByYear.value = sy
    topSuppliers.value = ts
    topProcurers.value = tp
    byCpv.value = cpv
    recent.value = r
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => filter.queryParams, load)

function fmtValue(v: number) {
  if (v >= 1_000_000_000) return `€ ${(v / 1_000_000_000).toFixed(2)}B`
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(0)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <div>
    <div class="mb-5">
      <h1 class="text-xl font-bold text-slate-900 dark:text-slate-100">{{ t('dashboard.title') }}</h1>
      <p class="text-xs text-slate-400 mt-0.5">{{ t('dashboard.subtitle') }}</p>
    </div>

    <div v-if="loading" class="text-slate-400 text-sm py-12 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm py-6">{{ error }}</div>

    <template v-else-if="summary">
      <!-- KPI cards -->
      <div class="grid grid-cols-4 gap-4 mb-5">
        <KpiCard :label="t('dashboard.totalValue')" :value="fmtValue(summary.total_value)" color="blue" delta="↑ +8.4%" />
        <KpiCard :label="t('dashboard.contractCount')" :value="summary.contract_count.toLocaleString()" color="green" delta="↑ +312" />
        <KpiCard :label="t('dashboard.avgValue')" :value="fmtValue(summary.avg_value)" color="red" delta="↓ −2.1%" :deltaDown="true" />
        <KpiCard :label="t('dashboard.activeSuppliers')" :value="summary.active_suppliers.toLocaleString()" color="purple" delta="↑ +124" />
      </div>

      <!-- Charts row -->
      <div class="grid grid-cols-3 gap-4 mb-5">
        <div class="col-span-2 bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.spendByYear') }}</p>
          <SpendBarChart :data="spendByYear" />
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.byCpv') }}</p>
          <CpvDonutChart :data="byCpv" />
        </div>
      </div>

      <!-- Bottom row -->
      <div class="grid grid-cols-2 gap-4">
        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.recentContracts') }}</p>
          <div class="space-y-2">
            <div
              v-for="c in recent"
              :key="c.id"
              class="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-700 text-xs"
            >
              <div class="truncate flex-1 mr-2">
                <p class="text-slate-700 dark:text-slate-300 truncate">{{ c.title }}</p>
                <p class="text-slate-400">{{ c.procurer_name }}</p>
              </div>
              <span class="font-bold text-blue-600 dark:text-sky-400 whitespace-nowrap">{{ fmtValue(c.value) }}</span>
            </div>
          </div>
        </div>

        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.topSuppliers') }}</p>
          <TopRankingList
            :items="topSuppliers.map(s => ({ ico: s.ico, name: s.name, value: s.total_value, count: s.contract_count }))"
            link-prefix="/suppliers"
          />
        </div>
      </div>
    </template>
  </div>
</template>

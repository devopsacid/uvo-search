<!-- src/uvo-gui-vuejs/src/pages/SupplierDetailPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntitySummary } from '../api/client'
import KpiCard from '../components/KpiCard.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import TopRankingList from '../components/TopRankingList.vue'
import ContractTable from '../components/ContractTable.vue'
import ContractSlideOver from '../components/ContractSlideOver.vue'

const route = useRoute()
const { t } = useI18n()
const ico = String(route.params.ico)

const summary = ref<EntitySummary | null>(null)
const detail = ref<Record<string, unknown> | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selected = ref(null)

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v}`
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, d] = await Promise.all([api.suppliers.summary(ico), api.suppliers.detail(ico)])
    summary.value = s
    detail.value = d
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
    <div v-if="loading" class="text-slate-400 text-sm py-12 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm py-6">{{ error }}</div>
    <template v-else-if="summary">
      <div class="flex items-center gap-3 mb-5">
        <div>
          <h1 class="text-xl font-bold">{{ summary.name }}</h1>
          <p class="text-xs text-slate-400 mt-0.5">IČO: {{ summary.ico }} · Dodávateľ</p>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-4 mb-5">
        <KpiCard label="Zákazky" :value="summary.contract_count.toLocaleString()" color="blue" />
        <KpiCard label="Celková hodnota" :value="fmt(summary.total_value ?? 0)" color="green" />
        <KpiCard label="Priemerná hodnota" :value="fmt(summary.avg_value)" color="red" />
        <KpiCard :label="t('dashboard.spendByYear')" :value="summary.spend_by_year.length + ' rokov'" color="purple" />
      </div>

      <div class="grid grid-cols-3 gap-4 mb-5">
        <div class="col-span-2 bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Trend výdavkov</p>
          <SpendBarChart :data="summary.spend_by_year" />
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Top obstarávatelia</p>
          <TopRankingList
            v-if="detail?.top_procurers"
            :items="(detail.top_procurers as any[]).map((p: any) => ({ ico: p.ico, name: p.name, value: p.total_value, count: p.contract_count }))"
            link-prefix="/procurers"
          />
        </div>
      </div>

      <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Zákazky</p>
        <ContractTable
          v-if="detail?.contracts"
          :rows="(detail.contracts as any[])"
          :total="(detail.contracts as any[]).length"
          :offset="0"
          :limit="100"
          @select="(r: any) => selected = r"
          @paginate="() => {}"
        />
      </div>
    </template>
    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>

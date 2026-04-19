<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntitySummary, ContractRow, ContractDetail } from '../api/client'
import Panel from '../components/Panel.vue'
import StatCard from '../components/StatCard.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import ContractTable from '../components/ContractTable.vue'
import ContractSlideOver from '../components/ContractSlideOver.vue'
import { fmtValue } from '../lib/format'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const ico = String(route.params.ico)

const summary = ref<EntitySummary | null>(null)
const detail = ref<Record<string, unknown> | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selected = ref<ContractDetail | null>(null)

interface TopProc { ico: string; name: string; total_value: number; contract_count: number }

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

async function selectRow(row: ContractRow) {
  try {
    selected.value = await api.contracts.detail(row.id)
  } catch {
    selected.value = { ...row, all_suppliers: [], publication_date: null }
  }
}

onMounted(load)
</script>

<template>
  <div v-if="loading && !summary" class="dim text-center py-16">{{ t('common.loading') }}</div>
  <div v-else-if="error" class="text-bad py-4">{{ error }}</div>

  <div v-else-if="summary" class="flex flex-col gap-3">
    <div class="flex items-baseline justify-between gap-3">
      <div>
        <p class="text-xs muted uppercase tracking-wider">{{ t('suppliers.title') }} · IČO <span class="mono">{{ summary.ico }}</span></p>
        <h2 class="text-xl font-semibold text-l-text dark:text-d-text">{{ summary.name }}</h2>
      </div>
      <button class="g-btn" @click="router.back()">← {{ t('common.back') }}</button>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard :label="t('entities.contracts')" :value="summary.contract_count.toLocaleString()" />
      <StatCard :label="t('suppliers.totalValue')" :value="fmtValue(summary.total_value ?? 0)" />
      <StatCard :label="t('entities.avgValue')" :value="fmtValue(summary.avg_value)" />
      <StatCard :label="t('entities.yearsActive')" :value="summary.spend_by_year.length.toString()" />
    </div>

    <Panel :title="t('entities.spendTrend')">
      <SpendBarChart :data="summary.spend_by_year" />
    </Panel>

    <Panel :title="t('entities.topProcurers')" dense>
      <div v-if="(detail?.top_procurers as TopProc[] | undefined)?.length" class="flex flex-col">
        <div
          v-for="(p, i) in (detail!.top_procurers as TopProc[])"
          :key="p.ico"
          class="g-row grid cursor-pointer"
          style="grid-template-columns: 40px 110px 1fr 120px 70px"
          @click="router.push(`/procurers/${p.ico}`)"
        >
          <span class="dim num">{{ (i + 1).toString().padStart(2, '0') }}</span>
          <span class="muted mono">{{ p.ico }}</span>
          <span class="truncate">{{ p.name }}</span>
          <span class="text-right font-semibold num">{{ fmtValue(p.total_value) }}</span>
          <span class="text-right dim num">{{ p.contract_count }}</span>
        </div>
      </div>
      <div v-else class="p-6 text-center dim text-xs">—</div>
    </Panel>

    <Panel :title="t('nav.contracts')" dense>
      <ContractTable
        v-if="detail?.contracts"
        :rows="(detail.contracts as ContractRow[])"
        :total="(detail.contracts as ContractRow[]).length"
        :offset="0"
        :limit="(detail.contracts as ContractRow[]).length"
        @select="selectRow"
        @paginate="() => {}"
      />
    </Panel>
  </div>

  <ContractSlideOver :contract="selected" @close="selected = null" />
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntitySummary, ContractRow, ContractDetail } from '../api/client'
import Panel from '../components/Panel.vue'
import Kpi from '../components/Kpi.vue'
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

interface TopSup { ico: string; name: string; total_value: number; contract_count: number }

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, d] = await Promise.all([api.procurers.summary(ico), api.procurers.detail(ico)])
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
  <div>
    <div v-if="loading && !summary" class="text-fg-dim text-xs py-12 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-down text-xs py-6">{{ error }}</div>

    <template v-else-if="summary">
      <div class="mb-2 flex items-baseline justify-between">
        <div>
          <p class="text-2xs text-fg-dim uppercase tracking-widest">{{ t('procurers.title') }} · IČO <span class="num">{{ summary.ico }}</span></p>
          <h1 class="text-xl text-fg-primary">{{ summary.name }}</h1>
        </div>
        <button class="t-button" @click="router.back()">◂ back</button>
      </div>

      <div class="grid grid-cols-12 gap-2 mb-2">
        <Panel :title="t('entities.keyMetrics')" class="col-span-4">
          <div class="flex flex-col">
            <Kpi :label="t('entities.contracts')" :value="summary.contract_count.toLocaleString()" />
            <Kpi :label="t('procurers.totalSpend')" :value="fmtValue(summary.total_spend ?? summary.total_value ?? 0)" />
            <Kpi :label="t('entities.avgValue')" :value="fmtValue(summary.avg_value)" />
            <Kpi :label="t('entities.yearsActive')" :value="summary.spend_by_year.length.toString()" />
          </div>
        </Panel>

        <Panel :title="t('entities.spendTrend')" class="col-span-8">
          <SpendBarChart :data="summary.spend_by_year" />
        </Panel>
      </div>

      <div class="grid grid-cols-12 gap-2 mb-2">
        <Panel :title="t('entities.topSuppliers')" class="col-span-12">
          <div
            v-if="(detail?.top_suppliers as TopSup[] | undefined)?.length"
            class="flex flex-col"
          >
            <div
              v-for="(s, i) in (detail!.top_suppliers as TopSup[])"
              :key="s.ico"
              class="t-row grid cursor-pointer px-1"
              style="grid-template-columns: 40px 100px 1fr 100px 80px"
              @click="router.push(`/suppliers/${s.ico}`)"
            >
              <span class="text-accent num">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="text-fg-muted num">{{ s.ico }}</span>
              <span class="text-fg-primary truncate">{{ s.name }}</span>
              <span class="text-right text-accent font-bold num">{{ fmtValue(s.total_value) }}</span>
              <span class="text-right text-fg-dim num">{{ s.contract_count }}</span>
            </div>
          </div>
          <div v-else class="text-fg-dim text-xs py-4 text-center">—</div>
        </Panel>
      </div>

      <Panel :title="t('nav.contracts')">
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
    </template>

    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>

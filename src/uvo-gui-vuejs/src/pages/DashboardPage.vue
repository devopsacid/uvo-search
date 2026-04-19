<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { DashboardSummary, SpendByYear, TopSupplier, TopProcurer, CpvShare, RecentContract } from '../api/client'
import Panel from '../components/Panel.vue'
import Kpi from '../components/Kpi.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import CpvDonutChart from '../components/CpvDonutChart.vue'
import { fmtValue } from '../lib/format'

const { t } = useI18n()
const router = useRouter()
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

function deltaOf(key: 'total_value' | 'contract_count' | 'avg_value' | 'active_suppliers') {
  const d = summary.value?.deltas?.[key]
  if (!d?.pct && d?.pct !== 0) return { text: undefined, dir: undefined as undefined | 'up' | 'down' }
  const pct = d.pct
  const sign = pct > 0 ? '+' : ''
  return { text: `${sign}${pct.toFixed(1)}%`, dir: (pct > 0 ? 'up' : pct < 0 ? 'down' : undefined) as 'up' | 'down' | undefined }
}

onMounted(load)
watch(() => filter.queryParams, load)

const latestYear = computed(() => spendByYear.value[spendByYear.value.length - 1]?.year)
</script>

<template>
  <div>
    <div class="mb-3 flex items-baseline justify-between">
      <h1 class="text-lg uppercase tracking-widest text-fg-primary">
        &gt; {{ t('dashboard.title') }}
      </h1>
      <span class="text-2xs text-fg-dim">{{ t('dashboard.subtitle') }}</span>
    </div>

    <div v-if="loading && !summary" class="text-fg-dim text-xs py-12 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-down text-xs py-6">{{ error }}</div>

    <template v-else-if="summary">
      <div class="grid grid-cols-12 gap-2 mb-2">
        <Panel :title="t('dashboard.keyMetrics')" class="col-span-4">
          <div class="flex flex-col gap-0">
            <Kpi
              :label="t('dashboard.totalValue')"
              :value="fmtValue(summary.total_value)"
              :delta="deltaOf('total_value').text"
              :deltaDir="deltaOf('total_value').dir"
            />
            <Kpi
              :label="t('dashboard.contractCount')"
              :value="summary.contract_count.toLocaleString()"
              :delta="deltaOf('contract_count').text"
              :deltaDir="deltaOf('contract_count').dir"
            />
            <Kpi
              :label="t('dashboard.avgValue')"
              :value="fmtValue(summary.avg_value)"
              :delta="deltaOf('avg_value').text"
              :deltaDir="deltaOf('avg_value').dir"
            />
            <Kpi
              :label="t('dashboard.activeSuppliers')"
              :value="summary.active_suppliers.toLocaleString()"
              :delta="deltaOf('active_suppliers').text"
              :deltaDir="deltaOf('active_suppliers').dir"
            />
          </div>
        </Panel>

        <Panel :title="`${t('dashboard.spendByYear')}${latestYear ? ' · ' + latestYear : ''}`" class="col-span-5">
          <SpendBarChart :data="spendByYear" />
        </Panel>

        <Panel :title="t('dashboard.byCpv')" class="col-span-3">
          <CpvDonutChart :data="byCpv" />
        </Panel>
      </div>

      <div class="grid grid-cols-12 gap-2 mb-2">
        <Panel :title="t('dashboard.topSuppliers')" class="col-span-6">
          <div class="flex flex-col">
            <div
              v-for="(s, i) in topSuppliers.slice(0, 8)"
              :key="s.ico"
              class="t-row grid cursor-pointer px-1"
              style="grid-template-columns: 32px 1fr 80px 60px"
              data-testid="top-supplier"
              @click="router.push(`/suppliers/${s.ico}`)"
            >
              <span class="text-accent num">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="text-fg-primary truncate">{{ s.name }}</span>
              <span class="text-right text-accent num">{{ fmtValue(s.total_value) }}</span>
              <span class="text-right text-fg-dim num">{{ s.contract_count }}</span>
            </div>
          </div>
        </Panel>

        <Panel :title="t('dashboard.topProcurers')" class="col-span-6">
          <div class="flex flex-col">
            <div
              v-for="(p, i) in topProcurers.slice(0, 8)"
              :key="p.ico"
              class="t-row grid cursor-pointer px-1"
              style="grid-template-columns: 32px 1fr 80px 60px"
              @click="router.push(`/procurers/${p.ico}`)"
            >
              <span class="text-accent num">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="text-fg-primary truncate">{{ p.name }}</span>
              <span class="text-right text-accent num">{{ fmtValue(p.total_spend) }}</span>
              <span class="text-right text-fg-dim num">{{ p.contract_count }}</span>
            </div>
          </div>
        </Panel>
      </div>

      <Panel :title="t('dashboard.recentContracts')">
        <div class="flex flex-col">
          <div
            v-for="c in recent"
            :key="c.id"
            class="t-row grid px-1"
            style="grid-template-columns: 70px 1fr 180px 90px 60px"
          >
            <span class="text-fg-dim num">{{ c.year }}</span>
            <span class="text-fg-primary truncate">{{ c.title }}</span>
            <span class="text-fg-muted truncate">{{ c.procurer_name }}</span>
            <span class="text-right text-accent num font-bold">{{ fmtValue(c.value) }}</span>
            <span class="text-right text-2xs uppercase" :class="c.status === 'active' ? 'text-up' : 'text-fg-dim'">
              {{ t(`contracts.status.${c.status}`) }}
            </span>
          </div>
          <div v-if="recent.length === 0" class="text-fg-dim text-xs py-4 text-center">—</div>
        </div>
      </Panel>
    </template>
  </div>
</template>

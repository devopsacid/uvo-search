<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { DashboardSummary, SpendByYear, TopSupplier, TopProcurer, CpvShare, RecentContract } from '../api/client'
import Panel from '../components/Panel.vue'
import StatCard from '../components/StatCard.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import CpvDonutChart from '../components/CpvDonutChart.vue'
import ContractStatusBadge from '../components/ContractStatusBadge.vue'
import { fmtValue, fmtPct } from '../lib/format'

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
  if (!d || d.pct == null) return { text: undefined, dir: undefined as 'up' | 'down' | 'flat' | undefined }
  return { text: fmtPct(d.pct), dir: (d.pct > 0 ? 'up' : d.pct < 0 ? 'down' : 'flat') as 'up' | 'down' | 'flat' }
}

onMounted(load)
watch(() => filter.queryParams, load)

const latestYear = computed(() => spendByYear.value[spendByYear.value.length - 1]?.year)
</script>

<template>
  <div v-if="loading && !summary" class="dim text-center py-16">{{ t('common.loading') }}</div>
  <div v-else-if="error" class="text-bad py-4">{{ error }}</div>

  <div v-else-if="summary" class="flex flex-col gap-3">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard
        :label="t('dashboard.totalValue')"
        :value="fmtValue(summary.total_value)"
        :delta="deltaOf('total_value').text"
        :delta-dir="deltaOf('total_value').dir"
        :sublabel="latestYear ? `${t('dashboard.vsYear')} ${latestYear - 1}` : undefined"
      />
      <StatCard
        :label="t('dashboard.contractCount')"
        :value="summary.contract_count.toLocaleString()"
        :delta="deltaOf('contract_count').text"
        :delta-dir="deltaOf('contract_count').dir"
      />
      <StatCard
        :label="t('dashboard.avgValue')"
        :value="fmtValue(summary.avg_value)"
        :delta="deltaOf('avg_value').text"
        :delta-dir="deltaOf('avg_value').dir"
      />
      <StatCard
        :label="t('dashboard.activeSuppliers')"
        :value="summary.active_suppliers.toLocaleString()"
      />
    </div>

    <div class="grid grid-cols-12 gap-3">
      <Panel :title="`${t('dashboard.spendByYear')}${latestYear ? ' · ' + latestYear : ''}`" class="col-span-12 xl:col-span-8">
        <SpendBarChart :data="spendByYear" />
      </Panel>
      <Panel :title="t('dashboard.byCpv')" class="col-span-12 xl:col-span-4">
        <CpvDonutChart :data="byCpv" :limit="7" />
      </Panel>
    </div>

    <div class="grid grid-cols-12 gap-3">
      <Panel :title="t('dashboard.topSuppliers')" class="col-span-12 md:col-span-6">
        <div class="flex flex-col">
          <div
            v-for="(s, i) in topSuppliers.slice(0, 8)"
            :key="s.ico"
            class="g-row grid cursor-pointer"
            style="grid-template-columns: 28px 1fr 100px 70px"
            @click="router.push(`/suppliers/${s.ico}`)"
          >
            <span class="dim num">{{ (i + 1).toString().padStart(2, '0') }}</span>
            <span class="truncate">{{ s.name }}</span>
            <span class="text-right font-semibold num">{{ s.total_value > 0 ? fmtValue(s.total_value) : '—' }}</span>
            <span class="text-right dim num">{{ s.contract_count }}</span>
          </div>
          <div v-if="topSuppliers.length === 0" class="py-6 text-center dim text-xs">—</div>
        </div>
      </Panel>

      <Panel :title="t('dashboard.topProcurers')" class="col-span-12 md:col-span-6">
        <div class="flex flex-col">
          <div
            v-for="(p, i) in topProcurers.slice(0, 8)"
            :key="p.ico"
            class="g-row grid cursor-pointer"
            style="grid-template-columns: 28px 1fr 100px 70px"
            @click="router.push(`/procurers/${p.ico}`)"
          >
            <span class="dim num">{{ (i + 1).toString().padStart(2, '0') }}</span>
            <span class="truncate">{{ p.name }}</span>
            <span class="text-right font-semibold num">{{ p.total_spend > 0 ? fmtValue(p.total_spend) : '—' }}</span>
            <span class="text-right dim num">{{ p.contract_count }}</span>
          </div>
          <div v-if="topProcurers.length === 0" class="py-6 text-center dim text-xs">—</div>
        </div>
      </Panel>
    </div>

    <Panel :title="t('dashboard.recentContracts')">
      <div class="flex flex-col">
        <div
          v-for="c in recent"
          :key="c.id"
          class="g-row grid"
          style="grid-template-columns: 70px 1fr 200px 110px 80px"
        >
          <span class="dim num">{{ c.year || '—' }}</span>
          <span class="truncate">{{ c.title }}</span>
          <span class="muted truncate">{{ c.procurer_name }}</span>
          <span class="text-right font-semibold num">{{ fmtValue(c.value) }}</span>
          <span class="text-center"><ContractStatusBadge :status="c.status" /></span>
        </div>
        <div v-if="recent.length === 0" class="py-6 text-center dim text-xs">—</div>
      </div>
    </Panel>
  </div>
</template>

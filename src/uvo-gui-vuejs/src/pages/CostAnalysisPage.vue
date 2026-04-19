<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { CpvShare, ContractRow } from '../api/client'
import Panel from '../components/Panel.vue'
import { fmtValue } from '../lib/format'
import { CHART_COLORS } from '../components/charts/chartDefaults'

const { t, locale } = useI18n()
const filter = useFilterStore()

const byCpv = ref<CpvShare[]>([])
const topContracts = ref<ContractRow[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

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
watch(() => filter.queryParams, load)

const cpvMax = computed(() => Math.max(...byCpv.value.map(c => c.percentage), 1))
</script>

<template>
  <div v-if="loading" class="dim text-center py-16">{{ t('common.loading') }}</div>
  <div v-else-if="error" class="text-bad py-4">{{ error }}</div>

  <div v-else class="flex flex-col gap-3">
    <Panel :title="t('costs.byCpv')">
      <div class="flex flex-col gap-1.5">
        <div
          v-for="(item, i) in byCpv"
          :key="item.cpv_code"
          class="grid items-center gap-3 text-xs"
          style="grid-template-columns: 70px 1fr 140px 100px 60px"
        >
          <span class="dim mono">{{ item.cpv_code }}</span>
          <span class="truncate muted">{{ locale === 'sk' ? item.label_sk : item.label_en }}</span>
          <span class="h-[6px] bg-l-panel-2 dark:bg-d-panel-2 rounded-sm overflow-hidden relative">
            <span
              class="absolute inset-y-0 left-0 rounded-sm"
              :style="{ width: `${(item.percentage / cpvMax) * 100}%`, background: CHART_COLORS.series[i % CHART_COLORS.series.length] }"
            />
          </span>
          <span class="text-right font-semibold num">{{ item.total_value > 0 ? fmtValue(item.total_value) : '—' }}</span>
          <span class="text-right dim num">{{ item.percentage.toFixed(1) }}%</span>
        </div>
        <div v-if="byCpv.length === 0" class="text-center py-6 dim text-xs">—</div>
      </div>
    </Panel>

    <Panel :title="t('costs.topContracts')">
      <div class="flex flex-col">
        <div
          v-for="(c, i) in topContracts"
          :key="c.id"
          class="g-row grid"
          style="grid-template-columns: 40px 1fr 200px 110px 60px"
        >
          <span class="dim num">{{ (i + 1).toString().padStart(2, '0') }}</span>
          <span class="truncate">{{ c.title }}</span>
          <span class="muted truncate">{{ c.procurer_name }}</span>
          <span class="text-right font-semibold num">{{ fmtValue(c.value) }}</span>
          <span class="text-right dim num">{{ c.year || '—' }}</span>
        </div>
      </div>
    </Panel>
  </div>
</template>

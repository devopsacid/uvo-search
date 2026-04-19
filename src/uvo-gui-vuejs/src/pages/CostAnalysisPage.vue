<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { CpvShare, ContractRow } from '../api/client'
import Panel from '../components/Panel.vue'
import { fmtValue } from '../lib/format'

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
  <div>
    <h1 class="text-lg uppercase tracking-widest mb-3">&gt; {{ t('costs.title') }}</h1>

    <div v-if="loading" class="text-fg-dim text-xs py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-down text-xs">{{ error }}</div>

    <template v-else>
      <Panel :title="t('costs.byCpv')" class="mb-2">
        <div class="flex flex-col gap-1">
          <div
            v-for="item in byCpv"
            :key="item.cpv_code"
            class="grid items-center gap-2 text-xs"
            style="grid-template-columns: 70px 1fr 140px 80px 60px"
          >
            <span class="text-fg-dim num">{{ item.cpv_code }}</span>
            <span class="truncate text-fg-muted">{{ locale === 'sk' ? item.label_sk : item.label_en }}</span>
            <span class="h-[4px] bg-ink-700 relative">
              <span class="absolute inset-y-0 left-0 bg-accent" :style="{ width: `${(item.percentage / cpvMax) * 100}%` }" />
            </span>
            <span class="text-right text-accent font-bold num">{{ fmtValue(item.total_value) }}</span>
            <span class="text-right text-fg-dim num">{{ item.percentage.toFixed(1) }}%</span>
          </div>
          <div v-if="byCpv.length === 0" class="text-fg-dim text-center py-4 text-xs">—</div>
        </div>
      </Panel>

      <Panel :title="t('costs.topContracts')">
        <div class="flex flex-col">
          <div
            v-for="(c, i) in topContracts"
            :key="c.id"
            class="t-row grid px-1"
            style="grid-template-columns: 40px 1fr 180px 90px 50px"
          >
            <span class="text-fg-dim num">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="text-fg-primary truncate">{{ c.title }}</span>
            <span class="text-fg-muted truncate">{{ c.procurer_name }}</span>
            <span class="text-right text-accent font-bold num">{{ fmtValue(c.value) }}</span>
            <span class="text-right text-fg-dim num">{{ c.year }}</span>
          </div>
        </div>
      </Panel>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { ContractRow, ContractDetail } from '../api/client'
import Panel from '../components/Panel.vue'
import ContractTable from '../components/ContractTable.vue'
import ContractSlideOver from '../components/ContractSlideOver.vue'

const { t } = useI18n()

const q = ref('')
const cpv = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const limit = 25
const offset = ref(0)
const total = ref(0)
const rows = ref<ContractRow[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const selected = ref<ContractDetail | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await api.contracts.list({
      q: q.value || undefined,
      cpv: cpv.value || undefined,
      date_from: dateFrom.value || undefined,
      date_to: dateTo.value || undefined,
      limit,
      offset: offset.value,
    })
    rows.value = res.data
    total.value = res.pagination.total
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

function search() { offset.value = 0; load() }
function paginate(newOffset: number) { offset.value = newOffset; load() }

onMounted(load)
</script>

<template>
  <div>
    <div class="mb-3 flex items-baseline justify-between">
      <h1 class="text-lg uppercase tracking-widest">&gt; {{ t('contracts.title') }}</h1>
      <span class="text-2xs text-fg-dim num">{{ total.toLocaleString() }} {{ t('contracts.total') }}</span>
    </div>

    <Panel :title="t('common.filter')" class="mb-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-accent">$</span>
        <input
          v-model="q"
          :placeholder="t('contracts.search')"
          class="t-input flex-1 min-w-48"
          @keydown.enter="search"
        />
        <input v-model="cpv" placeholder="CPV" class="t-input w-28" @keydown.enter="search" />
        <input v-model="dateFrom" type="date" class="t-input w-36" />
        <input v-model="dateTo" type="date" class="t-input w-36" />
        <button class="t-button" @click="search">▸ exec</button>
      </div>
    </Panel>

    <div v-if="loading && rows.length === 0" class="text-fg-dim text-xs py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-down text-xs py-4">{{ error }}</div>
    <ContractTable
      v-else
      :rows="rows"
      :total="total"
      :offset="offset"
      :limit="limit"
      @select="selectRow"
      @paginate="paginate"
    />

    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>

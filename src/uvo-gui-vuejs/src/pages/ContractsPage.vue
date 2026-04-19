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
  <div class="flex flex-col gap-3">
    <Panel :title="t('common.filter')">
      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="q"
          :placeholder="t('contracts.search')"
          class="g-input flex-1 min-w-[200px]"
          @keydown.enter="search"
        />
        <input v-model="cpv" placeholder="CPV" class="g-input w-28 mono" @keydown.enter="search" />
        <input v-model="dateFrom" type="date" class="g-input w-36" />
        <input v-model="dateTo" type="date" class="g-input w-36" />
        <button class="g-btn g-btn-primary" @click="search">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
          {{ t('contracts.searchBtn') }}
        </button>
      </div>
    </Panel>

    <Panel :title="t('contracts.title')" :loading="loading" dense>
      <div v-if="error" class="p-4 text-bad text-sm">{{ error }}</div>
      <ContractTable
        v-else
        :rows="rows"
        :total="total"
        :offset="offset"
        :limit="limit"
        @select="selectRow"
        @paginate="paginate"
      />
    </Panel>

    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>

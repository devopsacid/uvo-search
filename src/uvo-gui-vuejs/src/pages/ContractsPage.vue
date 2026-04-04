<!-- src/uvo-gui-vuejs/src/pages/ContractsPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { ContractRow, ContractDetail } from '../api/client'
import ContractTable from '../components/ContractTable.vue'
import ContractSlideOver from '../components/ContractSlideOver.vue'

const { t } = useI18n()

const q = ref('')
const cpv = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const limit = 20
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
    selected.value = { ...row, all_suppliers: [], publication_date: null, source_url: null }
  }
}

function search() { offset.value = 0; load() }
function paginate(newOffset: number) { offset.value = newOffset; load() }

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('contracts.title') }}</h1>

    <div class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm mb-4 flex flex-wrap gap-3">
      <input v-model="q" :placeholder="t('contracts.search')" class="flex-1 min-w-48 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" @keydown.enter="search" />
      <input v-model="cpv" placeholder="CPV kód" class="w-36 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" />
      <input v-model="dateFrom" type="date" class="w-40 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" />
      <input v-model="dateTo" type="date" class="w-40 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" />
      <button @click="search" class="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 transition-colors">Hľadať</button>
    </div>

    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm py-4">{{ error }}</div>
    <div v-else class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
      <ContractTable :rows="rows" :total="total" :offset="offset" :limit="limit" @select="selectRow" @paginate="paginate" />
    </div>

    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>

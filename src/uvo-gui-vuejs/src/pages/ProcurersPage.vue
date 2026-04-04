<!-- src/uvo-gui-vuejs/src/pages/ProcurersPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntityCard as EntityCardType } from '../api/client'
import EntityCard from '../components/EntityCard.vue'

const { t } = useI18n()
const q = ref('')
const items = ref<EntityCardType[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await api.procurers.list({ q: q.value || undefined })
    items.value = res.data
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
    <h1 class="text-xl font-bold mb-5">{{ t('procurers.title') }}</h1>
    <div class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm mb-4 flex gap-3">
      <input v-model="q" :placeholder="t('procurers.search')" class="flex-1 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" @keydown.enter="load" />
      <button @click="load" class="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 transition-colors">Hľadať</button>
    </div>
    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm">{{ error }}</div>
    <div v-else class="grid grid-cols-3 gap-4">
      <EntityCard
        v-for="p in items"
        :key="p.ico"
        :ico="p.ico"
        :name="p.name"
        :contract-count="p.contract_count"
        :total-value="p.total_spend ?? 0"
        link-prefix="/procurers"
        :contracts-label="t('procurers.contracts')"
      />
      <p v-if="items.length === 0" class="col-span-3 text-center text-slate-400 text-sm py-8">{{ t('procurers.noResults') }}</p>
    </div>
  </div>
</template>

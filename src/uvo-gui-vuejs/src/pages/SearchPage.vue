<!-- src/uvo-gui-vuejs/src/pages/SearchPage.vue -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ContractRow, EntityCard } from '../api/client'

const { t } = useI18n()
const router = useRouter()

const q = ref('')
const contracts = ref<ContractRow[]>([])
const suppliers = ref<EntityCard[]>([])
const procurers = ref<EntityCard[]>([])
const loading = ref(false)
const searched = ref(false)
const error = ref<string | null>(null)

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(1)}M`
  return `€ ${(v / 1_000).toFixed(0)}k`
}

async function search() {
  if (!q.value.trim()) return
  loading.value = true
  error.value = null
  searched.value = true
  try {
    const isIco = /^\d+$/.test(q.value.trim())
    const [c, s, p] = await Promise.all([
      api.contracts.list({ q: q.value, limit: 5 }),
      api.suppliers.list(isIco ? { ico: q.value } : { q: q.value }),
      api.procurers.list(isIco ? { ico: q.value } : { q: q.value }),
    ])
    contracts.value = c.data
    suppliers.value = s.data
    procurers.value = p.data
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

const hasResults = computed(() =>
  contracts.value.length + suppliers.value.length + procurers.value.length > 0
)
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('search.title') }}</h1>
    <div class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm mb-6 flex gap-3">
      <input
        v-model="q"
        :placeholder="t('search.placeholder')"
        class="flex-1 border border-slate-200 dark:border-slate-600 rounded px-3 py-2 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
        @keydown.enter="search"
      />
      <button @click="search" class="bg-blue-600 text-white px-5 py-2 rounded text-sm hover:bg-blue-700 transition-colors">Hľadať</button>
    </div>

    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm">{{ error }}</div>
    <div v-else-if="searched && !hasResults" class="text-slate-400 text-sm text-center py-8">{{ t('search.noResults') }}</div>

    <template v-else-if="searched">
      <div v-if="contracts.length" class="mb-6">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Zákazky ({{ contracts.length }})</h2>
        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm divide-y divide-slate-50 dark:divide-slate-700">
          <div v-for="c in contracts" :key="c.id" class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm" @click="router.push('/contracts')">
            <div>
              <p class="text-slate-800 dark:text-slate-200">{{ c.title }}</p>
              <p class="text-xs text-slate-400">{{ c.procurer_name }} · {{ c.year }}</p>
            </div>
            <span class="text-blue-600 dark:text-sky-400 font-bold text-xs">{{ fmt(c.value) }}</span>
          </div>
        </div>
      </div>

      <div v-if="suppliers.length" class="mb-6">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Dodávatelia ({{ suppliers.length }})</h2>
        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm divide-y divide-slate-50 dark:divide-slate-700">
          <div v-for="s in suppliers" :key="s.ico" class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm" @click="router.push(`/suppliers/${s.ico}`)">
            <div>
              <p class="text-slate-800 dark:text-slate-200">{{ s.name }}</p>
              <p class="text-xs text-slate-400">IČO: {{ s.ico }}</p>
            </div>
            <span class="text-xs text-slate-400">{{ s.contract_count }} zákaziek</span>
          </div>
        </div>
      </div>

      <div v-if="procurers.length">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Obstarávatelia ({{ procurers.length }})</h2>
        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm divide-y divide-slate-50 dark:divide-slate-700">
          <div v-for="p in procurers" :key="p.ico" class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm" @click="router.push(`/procurers/${p.ico}`)">
            <div>
              <p class="text-slate-800 dark:text-slate-200">{{ p.name }}</p>
              <p class="text-xs text-slate-400">IČO: {{ p.ico }}</p>
            </div>
            <span class="text-xs text-slate-400">{{ p.contract_count }} zákaziek</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

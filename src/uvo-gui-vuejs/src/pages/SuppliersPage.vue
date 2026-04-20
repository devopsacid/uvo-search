<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntityCard } from '../api/client'
import Panel from '../components/Panel.vue'
import EntityTable from '../components/EntityTable.vue'

const { t } = useI18n()
const q = ref('')
const items = ref<EntityCard[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await api.suppliers.list({ q: q.value || undefined })
    items.value = res.data
    total.value = res.pagination.total
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-3">
    <Panel :title="t('common.filter')">
      <div class="flex items-center gap-2">
        <input v-model="q" :placeholder="t('suppliers.search')" class="g-input flex-1" @keydown.enter="load" />
        <button class="g-btn g-btn-primary" @click="load">{{ t('contracts.searchBtn') }}</button>
      </div>
    </Panel>

    <Panel :title="`${t('suppliers.title')} · ${total.toLocaleString()}`" :loading="loading" dense>
      <div v-if="error" class="p-4 text-bad text-sm">{{ error }}</div>
      <div v-else-if="!loading && items.length === 0 && !q" class="p-6 flex flex-col items-center gap-2 text-center">
        <svg class="w-8 h-8 dim" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 9v4M12 17h.01M4.93 19.07A10 10 0 1 1 19.07 4.93 10 10 0 0 1 4.93 19.07z"/></svg>
        <p class="font-medium text-l-text dark:text-d-text">{{ t('suppliers.emptyTitle') }}</p>
        <p class="text-xs muted max-w-md">{{ t('suppliers.emptyHelp') }}</p>
      </div>
      <EntityTable
        v-else
        :rows="items"
        link-prefix="/suppliers"
        value-key="total_value"
        :value-label="t('suppliers.totalValue')"
      />
    </Panel>
  </div>
</template>

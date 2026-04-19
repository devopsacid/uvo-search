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
    const res = await api.procurers.list({ q: q.value || undefined })
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
        <input v-model="q" :placeholder="t('procurers.search')" class="g-input flex-1" @keydown.enter="load" />
        <button class="g-btn g-btn-primary" @click="load">{{ t('contracts.searchBtn') }}</button>
      </div>
    </Panel>

    <Panel :title="`${t('procurers.title')} · ${total.toLocaleString()}`" :loading="loading" dense>
      <div v-if="error" class="p-4 text-bad text-sm">{{ error }}</div>
      <EntityTable
        v-else
        :rows="items"
        link-prefix="/procurers"
        value-key="total_spend"
        :value-label="t('procurers.totalSpend')"
      />
    </Panel>
  </div>
</template>

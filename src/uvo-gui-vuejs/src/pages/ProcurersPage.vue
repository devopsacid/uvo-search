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
    <div class="mb-3 flex items-baseline justify-between">
      <h1 class="text-lg uppercase tracking-widest">&gt; {{ t('procurers.title') }}</h1>
      <span class="text-2xs text-fg-dim num">{{ items.length.toLocaleString() }}</span>
    </div>

    <Panel :title="t('common.filter')" class="mb-2">
      <div class="flex items-center gap-2">
        <span class="text-accent">$</span>
        <input
          v-model="q"
          :placeholder="t('procurers.search')"
          class="t-input flex-1"
          @keydown.enter="load"
        />
        <button class="t-button" @click="load">▸ exec</button>
      </div>
    </Panel>

    <div v-if="loading && items.length === 0" class="text-fg-dim text-xs py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-down text-xs">{{ error }}</div>
    <EntityTable
      v-else
      :rows="items"
      link-prefix="/procurers"
      value-key="total_spend"
      :value-label="t('procurers.totalSpend')"
    />
  </div>
</template>

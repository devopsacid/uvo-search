<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ContractRow, EntityCard } from '../api/client'
import Panel from '../components/Panel.vue'
import { fmtValue } from '../lib/format'

const { t } = useI18n()
const router = useRouter()

const q = ref('')
const contracts = ref<ContractRow[]>([])
const suppliers = ref<EntityCard[]>([])
const procurers = ref<EntityCard[]>([])
const loading = ref(false)
const searched = ref(false)
const error = ref<string | null>(null)
const inputEl = ref<HTMLInputElement | null>(null)

async function search() {
  if (!q.value.trim()) return
  loading.value = true
  error.value = null
  searched.value = true
  try {
    const isIco = /^\d+$/.test(q.value.trim())
    const [c, s, p] = await Promise.all([
      api.contracts.list({ q: q.value, limit: 10 }),
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

onMounted(async () => {
  await nextTick()
  inputEl.value?.focus()
})
</script>

<template>
  <div>
    <h1 class="text-lg uppercase tracking-widest mb-3">&gt; {{ t('search.title') }}</h1>

    <Panel :title="t('search.query')" class="mb-2">
      <div class="flex items-center gap-2">
        <span class="text-accent">$ search &gt;</span>
        <input
          ref="inputEl"
          v-model="q"
          :placeholder="t('search.placeholder')"
          class="t-input flex-1"
          @keydown.enter="search"
        />
        <button class="t-button" @click="search">▸ exec</button>
      </div>
    </Panel>

    <div v-if="loading" class="text-fg-dim text-xs py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-down text-xs">{{ error }}</div>
    <div v-else-if="searched && !hasResults" class="text-fg-dim text-xs text-center py-8">{{ t('search.noResults') }}</div>

    <template v-else-if="searched">
      <Panel v-if="contracts.length" :title="`${t('nav.contracts')} (${contracts.length})`" class="mb-2">
        <div class="flex flex-col">
          <div
            v-for="c in contracts"
            :key="c.id"
            class="t-row grid px-1 cursor-pointer"
            style="grid-template-columns: 60px 1fr 180px 90px"
            @click="router.push('/contracts')"
          >
            <span class="text-fg-dim num">{{ c.year }}</span>
            <span class="text-fg-primary truncate">{{ c.title }}</span>
            <span class="text-fg-muted truncate">{{ c.procurer_name }}</span>
            <span class="text-right text-accent font-bold num">{{ fmtValue(c.value) }}</span>
          </div>
        </div>
      </Panel>

      <Panel v-if="suppliers.length" :title="`${t('nav.suppliers')} (${suppliers.length})`" class="mb-2">
        <div class="flex flex-col">
          <div
            v-for="s in suppliers"
            :key="s.ico"
            class="t-row grid px-1 cursor-pointer"
            style="grid-template-columns: 100px 1fr 90px 70px"
            @click="router.push(`/suppliers/${s.ico}`)"
          >
            <span class="text-fg-muted num">{{ s.ico }}</span>
            <span class="text-fg-primary truncate">{{ s.name }}</span>
            <span class="text-right text-accent num">{{ fmtValue(s.total_value ?? 0) }}</span>
            <span class="text-right text-fg-dim num">{{ s.contract_count }}</span>
          </div>
        </div>
      </Panel>

      <Panel v-if="procurers.length" :title="`${t('nav.procurers')} (${procurers.length})`">
        <div class="flex flex-col">
          <div
            v-for="p in procurers"
            :key="p.ico"
            class="t-row grid px-1 cursor-pointer"
            style="grid-template-columns: 100px 1fr 90px 70px"
            @click="router.push(`/procurers/${p.ico}`)"
          >
            <span class="text-fg-muted num">{{ p.ico }}</span>
            <span class="text-fg-primary truncate">{{ p.name }}</span>
            <span class="text-right text-accent num">{{ fmtValue(p.total_spend ?? 0) }}</span>
            <span class="text-right text-fg-dim num">{{ p.contract_count }}</span>
          </div>
        </div>
      </Panel>
    </template>
  </div>
</template>

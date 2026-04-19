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
  <div class="flex flex-col gap-3">
    <Panel :title="t('search.query')">
      <div class="flex items-center gap-2">
        <input
          ref="inputEl"
          v-model="q"
          :placeholder="t('search.placeholder')"
          class="g-input flex-1"
          @keydown.enter="search"
        />
        <button class="g-btn g-btn-primary" @click="search">{{ t('contracts.searchBtn') }}</button>
      </div>
    </Panel>

    <div v-if="loading" class="dim text-center py-12">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-bad py-4">{{ error }}</div>
    <div v-else-if="searched && !hasResults" class="dim text-center py-12">{{ t('search.noResults') }}</div>

    <template v-else-if="searched">
      <Panel v-if="contracts.length" :title="`${t('nav.contracts')} · ${contracts.length}`" dense>
        <div class="flex flex-col">
          <div
            v-for="c in contracts"
            :key="c.id"
            class="g-row grid cursor-pointer"
            style="grid-template-columns: 70px 1fr 200px 110px"
            @click="router.push('/contracts')"
          >
            <span class="dim num">{{ c.year || '—' }}</span>
            <span class="truncate">{{ c.title }}</span>
            <span class="muted truncate">{{ c.procurer_name }}</span>
            <span class="text-right font-semibold num">{{ fmtValue(c.value) }}</span>
          </div>
        </div>
      </Panel>

      <Panel v-if="suppliers.length" :title="`${t('nav.suppliers')} · ${suppliers.length}`" dense>
        <div class="flex flex-col">
          <div
            v-for="s in suppliers"
            :key="s.ico"
            class="g-row grid cursor-pointer"
            style="grid-template-columns: 110px 1fr 110px 80px"
            @click="router.push(`/suppliers/${s.ico}`)"
          >
            <span class="muted mono">{{ s.ico }}</span>
            <span class="truncate">{{ s.name }}</span>
            <span class="text-right font-semibold num">{{ s.total_value != null && s.total_value > 0 ? fmtValue(s.total_value) : '—' }}</span>
            <span class="text-right dim num">{{ s.contract_count }}</span>
          </div>
        </div>
      </Panel>

      <Panel v-if="procurers.length" :title="`${t('nav.procurers')} · ${procurers.length}`" dense>
        <div class="flex flex-col">
          <div
            v-for="p in procurers"
            :key="p.ico"
            class="g-row grid cursor-pointer"
            style="grid-template-columns: 110px 1fr 110px 80px"
            @click="router.push(`/procurers/${p.ico}`)"
          >
            <span class="muted mono">{{ p.ico }}</span>
            <span class="truncate">{{ p.name }}</span>
            <span class="text-right font-semibold num">{{ p.total_spend != null && p.total_spend > 0 ? fmtValue(p.total_spend) : '—' }}</span>
            <span class="text-right dim num">{{ p.contract_count }}</span>
          </div>
        </div>
      </Panel>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { EntityHit } from '../api/client'
import { useFilterStore } from '../stores/filter'
import { fmtValue } from '../lib/format'

const props = withDefaults(defineProps<{
  /** If true, navigate to the entity detail page on select. Otherwise just apply the filter. */
  navigate?: boolean
}>(), { navigate: false })

const { t } = useI18n()
const router = useRouter()
const filter = useFilterStore()

const q = ref('')
const results = ref<EntityHit[]>([])
const loading = ref(false)
const open = ref(false)
const cursor = ref(0)
const rootEl = ref<HTMLElement | null>(null)

let debounceTimer: number | undefined
let latestRequest = 0

async function search(needle: string) {
  const myRequest = ++latestRequest
  loading.value = true
  try {
    const res = await api.search.entities(needle, 12)
    if (myRequest !== latestRequest) return
    results.value = res.items
    cursor.value = 0
  } catch {
    if (myRequest === latestRequest) results.value = []
  } finally {
    if (myRequest === latestRequest) loading.value = false
  }
}

watch(q, (val) => {
  open.value = true
  if (debounceTimer) window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => {
    void search(val.trim())
  }, 180)
})

onUnmounted(() => {
  if (debounceTimer) window.clearTimeout(debounceTimer)
})

function pick(hit: EntityHit) {
  filter.setCompany({ ico: hit.ico, name: hit.name, type: hit.type })
  q.value = ''
  results.value = []
  open.value = false
  if (props.navigate) {
    router.push(`${hit.type === 'supplier' ? '/suppliers' : '/procurers'}/${hit.ico}`)
  }
}

function onFocus() {
  open.value = true
  if (!q.value && results.value.length === 0) {
    void search('')
  }
}

async function onKey(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    open.value = true
    cursor.value = Math.min(cursor.value + 1, results.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    cursor.value = Math.max(cursor.value - 1, 0)
  } else if (e.key === 'Enter') {
    if (open.value && results.value[cursor.value]) {
      e.preventDefault()
      pick(results.value[cursor.value])
    }
  } else if (e.key === 'Escape') {
    open.value = false
    await nextTick()
  }
}

function onBlur() {
  // Delay to allow mousedown on list to fire first
  window.setTimeout(() => { open.value = false }, 150)
}
</script>

<template>
  <div ref="rootEl" class="relative">
    <div class="flex items-center gap-2 g-input">
      <svg class="w-3.5 h-3.5 dim shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input
        v-model="q"
        :placeholder="t('search.entityPlaceholder')"
        class="flex-1 bg-transparent outline-none border-0 p-0 text-sm min-w-0"
        @keydown="onKey"
        @focus="onFocus"
        @blur="onBlur"
      />
      <span v-if="loading" class="text-2xs dim">…</span>
      <button
        v-if="q"
        class="dim hover:text-bad text-xs shrink-0"
        @mousedown.prevent="q = ''"
        :title="t('common.clearFilter')"
      >✕</button>
    </div>

    <div
      v-if="open && (results.length > 0 || loading)"
      class="absolute left-0 right-0 top-full mt-1 panel max-h-80 overflow-y-auto z-30"
    >
      <ul>
        <li
          v-for="(hit, i) in results"
          :key="`${hit.type}-${hit.ico}`"
          class="flex items-center gap-3 px-3 py-2 cursor-pointer text-xs border-b border-l-border/50 dark:border-d-panel-2 last:border-b-0"
          :class="i === cursor ? 'bg-primary/10' : 'hover:bg-l-hover dark:hover:bg-d-hover'"
          @mouseenter="cursor = i"
          @mousedown.prevent="pick(hit)"
        >
          <span
            class="badge shrink-0"
            :class="hit.type === 'supplier' ? 'badge-good' : 'badge-dim'"
          >{{ hit.type === 'supplier' ? t('entities.supplier') : t('entities.procurer') }}</span>
          <span class="flex-1 truncate text-l-text dark:text-d-text">{{ hit.name }}</span>
          <span class="dim mono shrink-0">{{ hit.ico }}</span>
          <span class="num shrink-0 w-20 text-right">{{ hit.total_value > 0 ? fmtValue(hit.total_value) : '—' }}</span>
          <span class="dim num shrink-0 w-10 text-right">{{ hit.contract_count }}</span>
        </li>
        <li v-if="results.length === 0 && !loading" class="px-3 py-3 text-xs dim">
          {{ t('search.noResults') }}
        </li>
      </ul>
    </div>
  </div>
</template>

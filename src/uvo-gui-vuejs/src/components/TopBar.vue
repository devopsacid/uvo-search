<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useFilterStore } from '../stores/filter'
import { useCommandPalette } from '../composables/useCommandPalette'

const route = useRoute()
const { t, locale } = useI18n()
const filter = useFilterStore()
const palette = useCommandPalette()

const titleKey = computed(() => {
  const p = route.path
  if (p === '/') return 'dashboard.title'
  if (p.startsWith('/contracts')) return 'contracts.title'
  if (p.startsWith('/suppliers')) return 'suppliers.title'
  if (p.startsWith('/procurers')) return 'procurers.title'
  if (p.startsWith('/costs')) return 'costs.title'
  if (p.startsWith('/search')) return 'search.title'
  return 'dashboard.title'
})

function toggleLang() {
  locale.value = locale.value === 'sk' ? 'en' : 'sk'
}
</script>

<template>
  <header class="flex items-center h-12 border-b border-l-border dark:border-d-border bg-l-panel dark:bg-d-panel px-4 gap-3">
    <h1 class="text-sm font-semibold text-l-text dark:text-d-text truncate">{{ t(titleKey) }}</h1>

    <span v-if="filter.isFiltered" class="badge badge-good flex items-center gap-1 ml-2">
      <span class="truncate max-w-[220px]">{{ filter.name }}</span>
      <button class="dim hover:text-bad" @click="filter.clear()" :title="t('common.clearFilter')">✕</button>
    </span>

    <div class="flex-1" />

    <button class="g-btn" @click="palette.open()">
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <span class="hidden md:inline">{{ t('palette.placeholder') }}</span>
      <span class="text-2xs dim border border-l-border dark:border-d-border px-1 rounded-sm">⌘K</span>
    </button>

    <button data-testid="lang-toggle" class="g-btn" @click="toggleLang">
      {{ locale === 'sk' ? 'SK' : 'EN' }}
    </button>
  </header>
</template>

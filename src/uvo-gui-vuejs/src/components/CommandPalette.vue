<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useCommandPalette } from '../composables/useCommandPalette'

interface PaletteItem {
  kind: 'page' | 'action'
  label: string
  hint?: string
  action: () => void
}

const { t } = useI18n()
const router = useRouter()
const palette = useCommandPalette()

const q = ref('')
const cursor = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)

const pages = computed<PaletteItem[]>(() => [
  { kind: 'page', label: t('nav.dashboard'),  hint: 'g d', action: () => router.push('/') },
  { kind: 'page', label: t('nav.contracts'),  hint: 'g c', action: () => router.push('/contracts') },
  { kind: 'page', label: t('nav.suppliers'),  hint: 'g s', action: () => router.push('/suppliers') },
  { kind: 'page', label: t('nav.procurers'),  hint: 'g p', action: () => router.push('/procurers') },
  { kind: 'page', label: t('nav.costs'),      hint: 'g x', action: () => router.push('/costs') },
  { kind: 'page', label: t('nav.search'),     hint: '/',   action: () => router.push('/search') },
])

const results = computed<PaletteItem[]>(() => {
  const needle = q.value.trim().toLowerCase()
  if (!needle) return pages.value
  return pages.value.filter(p => p.label.toLowerCase().includes(needle))
})

watch(() => palette.isOpen.value, async (open) => {
  if (open) {
    q.value = ''
    cursor.value = 0
    await nextTick()
    inputEl.value?.focus()
  }
})

watch(results, () => { cursor.value = 0 })

function onKey(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    cursor.value = Math.min(cursor.value + 1, results.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    cursor.value = Math.max(cursor.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const item = results.value[cursor.value]
    if (item) { item.action(); palette.close() }
  }
}
</script>

<template>
  <div
    v-if="palette.isOpen.value"
    class="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/40"
    @click.self="palette.close()"
  >
    <div class="w-[640px] max-w-[90vw] panel">
      <div class="flex items-center gap-2 px-3 py-2 border-b border-l-border dark:border-d-border">
        <svg class="w-4 h-4 dim" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        <input
          ref="inputEl"
          v-model="q"
          :placeholder="t('palette.placeholder')"
          class="flex-1 bg-transparent outline-none text-sm text-l-text dark:text-d-text"
          @keydown="onKey"
        />
        <span class="text-2xs dim">esc</span>
      </div>

      <div v-if="results.length === 0" class="px-3 py-4 text-xs dim">
        {{ t('palette.noResults') }}
      </div>

      <ul v-else class="max-h-80 overflow-y-auto">
        <li
          v-for="(item, i) in results"
          :key="i"
          class="flex items-center justify-between px-3 py-2 cursor-pointer text-sm"
          :class="i === cursor ? 'bg-primary/10 text-primary' : 'text-l-text dark:text-d-text hover:bg-l-hover dark:hover:bg-d-hover'"
          @mouseenter="cursor = i"
          @click="item.action(); palette.close()"
        >
          <span class="flex items-center gap-3">
            <span class="text-2xs dim uppercase w-12">{{ item.kind }}</span>
            <span>{{ item.label }}</span>
          </span>
          <span v-if="item.hint" class="text-2xs dim border border-l-border dark:border-d-border px-1 rounded-sm">{{ item.hint }}</span>
        </li>
      </ul>

      <div class="flex items-center justify-between px-3 py-2 border-t border-l-border dark:border-d-border text-2xs dim">
        <span>↑↓ {{ t('palette.navigate') }} · ⏎ {{ t('palette.open') }} · esc {{ t('palette.close') }}</span>
        <span class="num">{{ results.length }} {{ t('palette.items') }}</span>
      </div>
    </div>
  </div>
</template>

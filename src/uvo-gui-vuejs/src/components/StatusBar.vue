<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCommandPalette } from '../composables/useCommandPalette'
import { fmtTs } from '../lib/format'

const { t, locale } = useI18n()
const palette = useCommandPalette()
const now = ref(new Date())

let timer: number | undefined

onMounted(() => {
  timer = window.setInterval(() => { now.value = new Date() }, 1000)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})

function toggleLang() {
  locale.value = locale.value === 'sk' ? 'en' : 'sk'
}
</script>

<template>
  <div class="flex items-center justify-between gap-4 px-4 py-1.5 bg-ink-800 border-t border-ink-600 text-2xs text-fg-dim tracking-wider">
    <div class="flex items-center gap-4 overflow-hidden whitespace-nowrap">
      <span>? {{ t('statusBar.help') }}</span>
      <span class="text-ink-500">·</span>
      <span>⌘K {{ t('statusBar.palette') }}</span>
      <span class="text-ink-500">·</span>
      <span>g d/c/s/p {{ t('statusBar.nav') }}</span>
      <span class="text-ink-500">·</span>
      <span>/ {{ t('statusBar.search') }}</span>
    </div>
    <div class="flex items-center gap-4 whitespace-nowrap">
      <button
        data-testid="lang-toggle"
        class="text-fg-muted hover:text-accent uppercase"
        @click="toggleLang"
      >[{{ locale === 'sk' ? 'SK' : 'EN' }}]</button>
      <span>{{ t('statusBar.palette') }}: <button class="text-fg-muted hover:text-accent" @click="palette.open()">⌘K</button></span>
      <span class="num">{{ fmtTs(now) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import TopNav from './components/TopNav.vue'
import { useThemeStore } from './stores/theme'

const theme = useThemeStore()
watch(() => theme.isDark, (dark) => {
  document.documentElement.classList.toggle('dark', dark)
}, { immediate: true })
</script>

<template>
  <div class="min-h-screen bg-slate-100 dark:bg-slate-900 text-slate-900 dark:text-slate-100 transition-colors">
    <TopNav />
    <main class="max-w-7xl mx-auto px-6 py-6">
      <RouterView />
    </main>
  </div>
</template>

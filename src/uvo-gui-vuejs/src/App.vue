<script setup lang="ts">
import TickerBar from './components/TickerBar.vue'
import TopNav from './components/TopNav.vue'
import StatusBar from './components/StatusBar.vue'
import CommandPalette from './components/CommandPalette.vue'
import { useHotkeys } from './composables/useHotkeys'

useHotkeys()
</script>

<template>
  <div class="flex flex-col h-screen bg-ink-950 text-fg-primary">
    <TickerBar />
    <TopNav />
    <main class="flex-1 overflow-y-auto">
      <div class="px-4 py-4">
        <RouterView />
      </div>
    </main>
    <StatusBar />
    <CommandPalette />
  </div>
</template>

<script setup lang="ts">
import Sidebar from './components/Sidebar.vue'
import TopBar from './components/TopBar.vue'
import CommandPalette from './components/CommandPalette.vue'
import { useHotkeys } from './composables/useHotkeys'

useHotkeys()
</script>

<template>
  <div class="flex h-screen bg-l-canvas dark:bg-d-canvas text-l-text dark:text-d-text">
    <Sidebar />
    <div class="flex-1 flex flex-col min-w-0">
      <TopBar />
      <main class="flex-1 overflow-y-auto">
        <div class="p-4">
          <RouterView />
        </div>
      </main>
    </div>
    <CommandPalette />
  </div>
</template>

<script setup lang="ts">
defineProps<{ title?: string; loading?: boolean; dense?: boolean }>()
</script>

<template>
  <section class="panel flex flex-col min-h-0">
    <header v-if="title || $slots.action" class="panel-header">
      <span class="truncate">{{ title }}</span>
      <span class="flex items-center gap-2">
        <span v-if="loading" class="text-xs dim animate-pulse">loading…</span>
        <slot name="action" />
      </span>
    </header>
    <div class="flex-1 min-h-0" :class="dense ? '' : 'panel-body'">
      <slot />
    </div>
  </section>
</template>

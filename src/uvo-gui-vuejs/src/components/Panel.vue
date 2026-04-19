<script setup lang="ts">
defineProps<{ title: string; loading?: boolean }>()
</script>

<template>
  <section class="panel flex flex-col">
    <header class="panel-header">
      <span>&gt; {{ title }}</span>
      <span v-if="loading" class="text-fg-dim animate-pulse">…</span>
      <slot name="action" />
    </header>
    <div class="panel-body flex-1 min-h-0">
      <slot />
    </div>
  </section>
</template>

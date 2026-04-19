<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  delta?: string
  deltaDir?: 'up' | 'down' | 'flat'
  sublabel?: string
}>()
</script>

<template>
  <section class="panel flex flex-col px-4 py-3">
    <div class="text-xs muted uppercase tracking-wider mb-1.5 truncate">{{ label }}</div>
    <div class="flex items-baseline gap-2">
      <span class="text-2xl font-semibold num">{{ value }}</span>
      <span
        v-if="delta"
        class="text-xs font-medium num"
        :class="{
          'text-good': deltaDir === 'up',
          'text-bad': deltaDir === 'down',
          'dim': !deltaDir || deltaDir === 'flat',
        }"
      >
        <span v-if="deltaDir === 'up'">▲</span><span v-else-if="deltaDir === 'down'">▼</span>
        {{ delta }}
      </span>
    </div>
    <div v-if="sublabel" class="text-xs dim mt-1 truncate">{{ sublabel }}</div>
  </section>
</template>

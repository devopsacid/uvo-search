<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  delta?: string
  deltaDir?: 'up' | 'down' | 'flat'
}>()
</script>

<template>
  <div class="flex items-center justify-between py-1 text-xs border-b border-ink-700 last:border-b-0">
    <span class="text-fg-muted">{{ label }}</span>
    <span class="flex items-baseline gap-2">
      <span class="text-fg-primary font-bold num">{{ value }}</span>
      <span
        v-if="delta"
        class="text-2xs num"
        :class="{
          'text-up': deltaDir === 'up',
          'text-down': deltaDir === 'down',
          'text-fg-dim': !deltaDir || deltaDir === 'flat',
        }"
      >{{ delta }}</span>
    </span>
  </div>
</template>

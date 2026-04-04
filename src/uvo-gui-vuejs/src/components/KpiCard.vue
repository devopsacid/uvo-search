<script setup lang="ts">
defineProps<{
  label: string
  value: string
  color: 'blue' | 'green' | 'red' | 'purple'
  delta?: string
  deltaDown?: boolean
}>()

const borderColors = {
  blue: 'border-blue-600',
  green: 'border-green-600',
  red: 'border-red-600',
  purple: 'border-purple-600',
}
</script>

<template>
  <div
    class="bg-white dark:bg-slate-800 rounded-lg p-4 border-l-4 shadow-sm"
    :class="borderColors[color]"
  >
    <p class="text-xs uppercase tracking-widest text-slate-400 mb-1">{{ label }}</p>
    <p class="text-2xl font-bold text-slate-900 dark:text-slate-100">{{ value }}</p>
    <p v-if="delta" class="text-xs mt-1" :class="deltaDown ? 'text-red-500' : 'text-green-500'">
      {{ delta }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

defineProps<{
  ico: string
  name: string
  contractCount: number
  totalValue: number
  linkPrefix: string
  contractsLabel: string
}>()

const router = useRouter()

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <div
    class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm cursor-pointer hover:shadow-md hover:ring-1 hover:ring-blue-200 dark:hover:ring-sky-800 transition-all"
    @click="router.push(`${linkPrefix}/${ico}`)"
  >
    <p class="font-semibold text-sm text-slate-800 dark:text-slate-200 mb-2 leading-tight line-clamp-2">{{ name }}</p>
    <p class="text-xs text-slate-400 mb-1">IČO: {{ ico }}</p>
    <div class="flex items-center justify-between mt-2">
      <span class="text-xs text-slate-500">{{ contractCount }} {{ contractsLabel }}</span>
      <span class="text-sm font-bold text-blue-600 dark:text-sky-400">{{ fmt(totalValue) }}</span>
    </div>
  </div>
</template>

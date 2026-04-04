<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

interface RankItem { ico: string; name: string; value: number; count: number }

const props = defineProps<{ items: RankItem[]; linkPrefix: string }>()
const router = useRouter()

const maxValue = computed(() => Math.max(...props.items.map(i => i.value), 1))

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <div class="space-y-2">
    <div
      v-for="(item, i) in items"
      :key="item.ico"
      class="flex items-center gap-2 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700 rounded px-1 py-1 transition-colors"
      @click="router.push(`${linkPrefix}/${item.ico}`)"
    >
      <span class="text-xs font-bold text-slate-300 w-4">{{ i + 1 }}</span>
      <span class="flex-1 text-xs text-slate-700 dark:text-slate-300 truncate">{{ item.name }}</span>
      <div class="w-20 h-1.5 bg-slate-100 dark:bg-slate-700 rounded">
        <div class="h-1.5 bg-blue-600 dark:bg-sky-400 rounded" :style="{ width: `${(item.value / maxValue) * 100}%` }" />
      </div>
      <span class="text-xs text-slate-500 w-14 text-right">{{ fmt(item.value) }}</span>
    </div>
  </div>
</template>

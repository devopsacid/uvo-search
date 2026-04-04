<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractRow } from '../api/client'

const props = defineProps<{
  rows: ContractRow[]
  total: number
  offset: number
  limit: number
}>()

const emit = defineEmits<{
  select: [row: ContractRow]
  paginate: [offset: number]
}>()

const { t } = useI18n()

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}

const hasPrev = () => props.offset > 0
const hasNext = () => props.offset + props.limit < props.total
</script>

<template>
  <div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-slate-100 dark:border-slate-700">
            <th class="text-left text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.title') }}</th>
            <th class="text-left text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.procurer') }}</th>
            <th class="text-left text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.supplier') }}</th>
            <th class="text-right text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.value') }}</th>
            <th class="text-center text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.year') }}</th>
            <th class="text-center text-xs uppercase tracking-wider text-slate-400 pb-2">{{ t('contracts.columns.status') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b border-slate-50 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
            @click="emit('select', row)"
          >
            <td class="py-2 pr-4 text-slate-700 dark:text-slate-300 truncate max-w-xs">{{ row.title }}</td>
            <td class="py-2 pr-4 text-slate-600 dark:text-slate-400 text-xs">{{ row.procurer_name }}</td>
            <td class="py-2 pr-4 text-slate-600 dark:text-slate-400 text-xs">{{ row.supplier_name ?? '—' }}</td>
            <td class="py-2 pr-4 text-right font-mono text-xs text-slate-700 dark:text-slate-300">{{ fmt(row.value) }}</td>
            <td class="py-2 pr-4 text-center text-xs text-slate-500">{{ row.year }}</td>
            <td class="py-2 text-center">
              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium"
                :class="row.status === 'active' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' : 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'"
              >
                {{ t(`contracts.status.${row.status}`) }}
              </span>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="6" class="py-6 text-center text-slate-400 text-sm">{{ t('contracts.noResults') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex items-center justify-between mt-3">
      <span class="text-xs text-slate-400">{{ total }} total</span>
      <div class="flex gap-2">
        <button
          :disabled="!hasPrev()"
          class="text-xs px-3 py-1 rounded bg-slate-100 dark:bg-slate-700 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
          @click="emit('paginate', offset - limit)"
        >{{ t('common.pagination.prev') }}</button>
        <button
          :disabled="!hasNext()"
          class="text-xs px-3 py-1 rounded bg-slate-100 dark:bg-slate-700 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
          @click="emit('paginate', offset + limit)"
        >{{ t('common.pagination.next') }}</button>
      </div>
    </div>
  </div>
</template>

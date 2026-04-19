<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractRow } from '../api/client'
import ContractStatusBadge from './ContractStatusBadge.vue'
import { fmtValue } from '../lib/format'

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

const hasPrev = () => props.offset > 0
const hasNext = () => props.offset + props.limit < props.total
const pageEnd = () => Math.min(props.offset + props.limit, props.total)
</script>

<template>
  <div class="flex flex-col">
    <div class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead class="bg-l-panel-2 dark:bg-d-panel-2 text-l-muted dark:text-d-muted">
          <tr>
            <th class="text-left font-medium px-3 py-2 w-[70px]">#</th>
            <th class="text-left font-medium px-3 py-2">{{ t('contracts.columns.title') }}</th>
            <th class="text-left font-medium px-3 py-2 w-[200px]">{{ t('contracts.columns.procurer') }}</th>
            <th class="text-right font-medium px-3 py-2 w-[110px]">{{ t('contracts.columns.value') }}</th>
            <th class="text-center font-medium px-3 py-2 w-[70px]">{{ t('contracts.columns.year') }}</th>
            <th class="text-center font-medium px-3 py-2 w-[100px]">{{ t('contracts.columns.status') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, i) in rows"
            :key="row.id"
            class="border-b border-l-border/50 dark:border-d-panel-2 hover:bg-l-hover dark:hover:bg-d-hover cursor-pointer"
            data-testid="contract-row"
            @click="emit('select', row)"
          >
            <td class="px-3 py-2 dim num">{{ (offset + i + 1).toString().padStart(4, '0') }}</td>
            <td class="px-3 py-2 text-l-text dark:text-d-text truncate max-w-0">{{ row.title }}</td>
            <td class="px-3 py-2 muted truncate max-w-0">{{ row.procurer_name }}</td>
            <td class="px-3 py-2 text-right font-semibold num">{{ fmtValue(row.value) }}</td>
            <td class="px-3 py-2 text-center muted num">{{ row.year || '—' }}</td>
            <td class="px-3 py-2 text-center"><ContractStatusBadge :status="row.status" /></td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="6" class="py-8 text-center dim">{{ t('contracts.noResults') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex items-center justify-between px-3 py-2 text-xs muted border-t border-l-border dark:border-d-border">
      <span>
        <span class="num">{{ (offset + 1).toLocaleString() }}–{{ pageEnd().toLocaleString() }}</span>
        &nbsp;/&nbsp;<span class="num">{{ total.toLocaleString() }}</span>
      </span>
      <div class="flex gap-2">
        <button class="g-btn" :disabled="!hasPrev()" @click="emit('paginate', Math.max(0, offset - limit))">
          ← {{ t('common.pagination.prev') }}
        </button>
        <button class="g-btn" :disabled="!hasNext()" @click="emit('paginate', offset + limit)">
          {{ t('common.pagination.next') }} →
        </button>
      </div>
    </div>
  </div>
</template>

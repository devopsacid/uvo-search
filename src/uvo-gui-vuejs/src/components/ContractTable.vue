<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractRow } from '../api/client'
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
    <div class="overflow-x-auto border border-ink-600">
      <table class="w-full text-xs num">
        <thead class="bg-ink-800 sticky top-0">
          <tr>
            <th class="text-left label px-2 py-1.5 border-b border-ink-600 w-[60px]">ID</th>
            <th class="text-left label px-2 py-1.5 border-b border-ink-600">{{ t('contracts.columns.title') }}</th>
            <th class="text-left label px-2 py-1.5 border-b border-ink-600 w-[180px]">{{ t('contracts.columns.procurer') }}</th>
            <th class="text-left label px-2 py-1.5 border-b border-ink-600 w-[180px]">{{ t('contracts.columns.supplier') }}</th>
            <th class="text-right label px-2 py-1.5 border-b border-ink-600 w-[90px]">{{ t('contracts.columns.value') }}</th>
            <th class="text-center label px-2 py-1.5 border-b border-ink-600 w-[60px]">{{ t('contracts.columns.year') }}</th>
            <th class="text-center label px-2 py-1.5 border-b border-ink-600 w-[70px]">{{ t('contracts.columns.status') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, i) in rows"
            :key="row.id"
            class="cursor-pointer hover:bg-ink-800 border-b border-ink-700"
            data-testid="contract-row"
            @click="emit('select', row)"
          >
            <td class="px-2 py-1 text-fg-dim">{{ String(offset + i + 1).padStart(4, '0') }}</td>
            <td class="px-2 py-1 text-fg-primary truncate max-w-0">{{ row.title }}</td>
            <td class="px-2 py-1 text-fg-muted truncate max-w-0">{{ row.procurer_name }}</td>
            <td class="px-2 py-1 text-fg-muted truncate max-w-0">{{ row.supplier_name ?? '—' }}</td>
            <td class="px-2 py-1 text-right text-accent font-bold">{{ fmtValue(row.value) }}</td>
            <td class="px-2 py-1 text-center text-fg-muted">{{ row.year }}</td>
            <td class="px-2 py-1 text-center">
              <span
                class="text-2xs uppercase tracking-wider"
                :class="row.status === 'active' ? 'text-up' : 'text-fg-dim'"
              >{{ t(`contracts.status.${row.status}`) }}</span>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="7" class="py-6 text-center text-fg-dim">{{ t('contracts.noResults') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex items-center justify-between mt-2 text-2xs text-fg-dim">
      <span>
        <span class="text-fg-muted num">{{ offset + 1 }}–{{ pageEnd() }}</span>
        / <span class="text-fg-muted num">{{ total.toLocaleString() }}</span>
      </span>
      <div class="flex gap-2">
        <button class="t-button" :disabled="!hasPrev()" @click="emit('paginate', Math.max(0, offset - limit))">
          ◂ {{ t('common.pagination.prev') }}
        </button>
        <button class="t-button" :disabled="!hasNext()" @click="emit('paginate', offset + limit)">
          {{ t('common.pagination.next') }} ▸
        </button>
      </div>
    </div>
  </div>
</template>

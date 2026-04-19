<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { EntityCard } from '../api/client'
import { fmtValue } from '../lib/format'

const props = defineProps<{
  rows: EntityCard[]
  linkPrefix: '/suppliers' | '/procurers'
  valueKey: 'total_value' | 'total_spend'
  valueLabel: string
}>()

const { t } = useI18n()
const router = useRouter()

function getValue(r: EntityCard): number {
  return (r[props.valueKey] as number | undefined) ?? 0
}

function go(ico: string) {
  router.push(`${props.linkPrefix}/${ico}`)
}
</script>

<template>
  <div class="overflow-x-auto border border-ink-600">
    <table class="w-full text-xs num">
      <thead class="bg-ink-800">
        <tr>
          <th class="label text-left px-2 py-1.5 border-b border-ink-600 w-[50px]">#</th>
          <th class="label text-left px-2 py-1.5 border-b border-ink-600 w-[100px]">IČO</th>
          <th class="label text-left px-2 py-1.5 border-b border-ink-600">{{ t('entities.name') }}</th>
          <th class="label text-right px-2 py-1.5 border-b border-ink-600 w-[90px]">{{ valueLabel }}</th>
          <th class="label text-right px-2 py-1.5 border-b border-ink-600 w-[90px]">{{ t('entities.contracts') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(r, i) in rows"
          :key="r.ico"
          class="cursor-pointer hover:bg-ink-800 border-b border-ink-700"
          data-testid="entity-row"
          @click="go(r.ico)"
        >
          <td class="px-2 py-1 text-fg-dim">{{ String(i + 1).padStart(3, '0') }}</td>
          <td class="px-2 py-1 text-fg-muted">{{ r.ico }}</td>
          <td class="px-2 py-1 text-fg-primary truncate max-w-0">{{ r.name }}</td>
          <td class="px-2 py-1 text-right text-accent font-bold">{{ fmtValue(getValue(r)) }}</td>
          <td class="px-2 py-1 text-right text-fg-muted">{{ r.contract_count.toLocaleString() }}</td>
        </tr>
        <tr v-if="rows.length === 0">
          <td colspan="5" class="py-6 text-center text-fg-dim">—</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

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

function go(ico: string) { router.push(`${props.linkPrefix}/${ico}`) }
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full text-xs">
      <thead class="bg-l-panel-2 dark:bg-d-panel-2 text-l-muted dark:text-d-muted">
        <tr>
          <th class="text-left font-medium px-3 py-2 w-[60px]">#</th>
          <th class="text-left font-medium px-3 py-2 w-[110px]">IČO</th>
          <th class="text-left font-medium px-3 py-2">{{ t('entities.name') }}</th>
          <th class="text-right font-medium px-3 py-2 w-[110px]">{{ valueLabel }}</th>
          <th class="text-right font-medium px-3 py-2 w-[110px]">{{ t('entities.contracts') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(r, i) in rows"
          :key="r.ico"
          class="border-b border-l-border/50 dark:border-d-panel-2 hover:bg-l-hover dark:hover:bg-d-hover cursor-pointer"
          data-testid="entity-row"
          @click="go(r.ico)"
        >
          <td class="px-3 py-2 dim num">{{ (i + 1).toString().padStart(3, '0') }}</td>
          <td class="px-3 py-2 muted mono">{{ r.ico }}</td>
          <td class="px-3 py-2 text-l-text dark:text-d-text truncate max-w-0">{{ r.name }}</td>
          <td class="px-3 py-2 text-right font-semibold num">{{ getValue(r) > 0 ? fmtValue(getValue(r)) : '—' }}</td>
          <td class="px-3 py-2 text-right muted num">{{ r.contract_count.toLocaleString() }}</td>
        </tr>
        <tr v-if="rows.length === 0">
          <td colspan="5" class="py-8 text-center dim">—</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

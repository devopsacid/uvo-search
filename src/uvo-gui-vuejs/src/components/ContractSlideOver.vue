<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractDetail } from '../api/client'

defineProps<{ contract: ContractDetail | null }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <Transition name="slide">
    <div
      v-if="contract"
      class="fixed inset-y-0 right-0 w-96 bg-white dark:bg-slate-800 shadow-2xl z-40 overflow-y-auto"
    >
      <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-700">
        <h3 class="font-semibold text-sm text-slate-800 dark:text-slate-200">Detail zákazky</h3>
        <button @click="emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-lg leading-none">✕</button>
      </div>

      <div class="px-5 py-4 space-y-4 text-sm">
        <div>
          <p class="text-xs text-slate-400 uppercase tracking-wider mb-1">Zákazka</p>
          <p class="font-medium text-slate-800 dark:text-slate-200">{{ contract.title }}</p>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <p class="text-xs text-slate-400 mb-0.5">{{ t('contracts.columns.value') }}</p>
            <p class="font-bold text-blue-600 dark:text-sky-400">{{ fmt(contract.value) }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-400 mb-0.5">{{ t('contracts.columns.year') }}</p>
            <p class="font-medium">{{ contract.year }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-400 mb-0.5">{{ t('contracts.columns.procurer') }}</p>
            <p class="text-slate-700 dark:text-slate-300">{{ contract.procurer_name }}</p>
            <p class="text-xs text-slate-400">IČO: {{ contract.procurer_ico }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-400 mb-0.5">CPV</p>
            <p class="text-slate-600 dark:text-slate-400 font-mono text-xs">{{ contract.cpv_code ?? '—' }}</p>
          </div>
        </div>

        <div v-if="contract.all_suppliers?.length">
          <p class="text-xs text-slate-400 uppercase tracking-wider mb-2">Dodávatelia</p>
          <div v-for="s in contract.all_suppliers" :key="s.ico" class="text-xs py-1 border-b border-slate-50 dark:border-slate-700">
            {{ s.nazov }} <span class="text-slate-400 ml-1">IČO: {{ s.ico }}</span>
          </div>
        </div>

        <div v-if="contract.publication_date">
          <p class="text-xs text-slate-400 mb-0.5">Dátum zverejnenia</p>
          <p class="text-xs text-slate-600 dark:text-slate-400">{{ contract.publication_date }}</p>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: transform 0.2s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>

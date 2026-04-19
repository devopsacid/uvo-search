<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractDetail } from '../api/client'
import ContractStatusBadge from './ContractStatusBadge.vue'
import { fmtValue } from '../lib/format'

defineProps<{ contract: ContractDetail | null }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
</script>

<template>
  <Transition name="slide">
    <aside
      v-if="contract"
      class="fixed inset-y-0 right-0 w-[440px] max-w-full bg-l-panel dark:bg-d-panel border-l border-l-border dark:border-d-border z-40 overflow-y-auto flex flex-col shadow-panel"
    >
      <header class="flex items-center justify-between px-4 h-12 border-b border-l-border dark:border-d-border">
        <span class="text-sm font-semibold text-l-text dark:text-d-text">{{ t('contracts.detail') }}</span>
        <button class="g-btn" @click="emit('close')">✕ esc</button>
      </header>

      <div class="p-4 flex flex-col gap-4 text-sm">
        <div>
          <p class="text-xs muted uppercase tracking-wider mb-1">{{ t('contracts.columns.title') }}</p>
          <p class="text-l-text dark:text-d-text font-medium leading-snug">{{ contract.title }}</p>
          <p class="text-xs dim mt-1 mono">ID · {{ contract.id }}</p>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <p class="text-xs muted uppercase tracking-wider mb-1">{{ t('contracts.columns.value') }}</p>
            <p class="text-lg font-semibold text-primary num">{{ fmtValue(contract.value) }}</p>
          </div>
          <div>
            <p class="text-xs muted uppercase tracking-wider mb-1">{{ t('contracts.columns.year') }}</p>
            <p class="num">{{ contract.year || '—' }}</p>
          </div>
          <div>
            <p class="text-xs muted uppercase tracking-wider mb-1">{{ t('contracts.columns.procurer') }}</p>
            <p class="text-l-text dark:text-d-text truncate">{{ contract.procurer_name }}</p>
            <p class="text-xs dim mt-0.5 mono">IČO · {{ contract.procurer_ico }}</p>
          </div>
          <div>
            <p class="text-xs muted uppercase tracking-wider mb-1">CPV</p>
            <p class="mono muted">{{ contract.cpv_code || '—' }}</p>
          </div>
          <div>
            <p class="text-xs muted uppercase tracking-wider mb-1">{{ t('contracts.columns.status') }}</p>
            <ContractStatusBadge :status="contract.status" />
          </div>
          <div v-if="contract.publication_date">
            <p class="text-xs muted uppercase tracking-wider mb-1">{{ t('contracts.publicationDate') }}</p>
            <p class="muted num">{{ contract.publication_date }}</p>
          </div>
        </div>

        <div v-if="contract.all_suppliers?.length">
          <p class="text-xs muted uppercase tracking-wider mb-2">{{ t('contracts.suppliers') }}</p>
          <div
            v-for="s in contract.all_suppliers"
            :key="String(s.ico || s.supplier_ico || s.name)"
            class="flex items-center justify-between py-1.5 border-b border-l-border/50 dark:border-d-panel-2 muted"
          >
            <span class="truncate mr-2">{{ s.supplier_name || s.name }}</span>
            <span class="dim mono">{{ s.supplier_ico || s.ico }}</span>
          </div>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: transform 0.15s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>

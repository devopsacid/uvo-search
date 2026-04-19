<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractDetail } from '../api/client'
import { fmtValue } from '../lib/format'

defineProps<{ contract: ContractDetail | null }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
</script>

<template>
  <Transition name="slide">
    <aside
      v-if="contract"
      class="fixed inset-y-0 right-0 w-[420px] max-w-full bg-ink-950 border-l border-ink-600 z-40 overflow-y-auto flex flex-col"
    >
      <header class="flex items-center justify-between px-3 py-2 bg-ink-800 border-b border-ink-600">
        <span class="text-accent text-xs uppercase tracking-widest font-bold">&gt; {{ t('contracts.detail') }}</span>
        <button class="text-fg-muted hover:text-accent text-sm" @click="emit('close')">✕ esc</button>
      </header>

      <div class="px-3 py-3 space-y-4 text-xs">
        <div>
          <p class="label mb-1">{{ t('contracts.columns.title') }}</p>
          <p class="text-fg-primary text-sm leading-tight">{{ contract.title }}</p>
          <p class="text-fg-dim mt-1">ID: <span class="num">{{ contract.id }}</span></p>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <p class="label mb-1">{{ t('contracts.columns.value') }}</p>
            <p class="text-accent font-bold text-base num">{{ fmtValue(contract.value) }}</p>
          </div>
          <div>
            <p class="label mb-1">{{ t('contracts.columns.year') }}</p>
            <p class="text-fg-primary num">{{ contract.year }}</p>
          </div>
          <div>
            <p class="label mb-1">{{ t('contracts.columns.procurer') }}</p>
            <p class="text-fg-primary truncate">{{ contract.procurer_name }}</p>
            <p class="text-fg-dim mt-0.5 num">IČO {{ contract.procurer_ico }}</p>
          </div>
          <div>
            <p class="label mb-1">CPV</p>
            <p class="text-fg-muted num">{{ contract.cpv_code ?? '—' }}</p>
          </div>
          <div>
            <p class="label mb-1">{{ t('contracts.columns.status') }}</p>
            <p :class="contract.status === 'active' ? 'text-up' : 'text-fg-dim'">
              {{ t(`contracts.status.${contract.status}`) }}
            </p>
          </div>
          <div v-if="contract.publication_date">
            <p class="label mb-1">{{ t('contracts.publicationDate') }}</p>
            <p class="text-fg-muted num">{{ contract.publication_date }}</p>
          </div>
        </div>

        <div v-if="contract.all_suppliers?.length">
          <p class="label mb-2">{{ t('contracts.suppliers') }}</p>
          <div
            v-for="s in contract.all_suppliers"
            :key="String(s.ico)"
            class="flex items-center justify-between py-1 border-b border-ink-700 text-fg-muted"
          >
            <span class="truncate mr-2">{{ s.nazov }}</span>
            <span class="text-fg-dim num">{{ s.ico }}</span>
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

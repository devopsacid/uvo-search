<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ status: string | null | undefined }>()
const { t } = useI18n()

const STATUS_MAP: Record<string, { cls: string; key: string }> = {
  active:   { cls: 'badge-good', key: 'contracts.status.active' },
  awarded:  { cls: 'badge-good', key: 'contracts.status.awarded' },
  open:     { cls: 'badge-good', key: 'contracts.status.open' },
  closed:   { cls: 'badge-dim',  key: 'contracts.status.closed' },
  completed:{ cls: 'badge-dim',  key: 'contracts.status.completed' },
  cancelled:{ cls: 'badge-bad',  key: 'contracts.status.cancelled' },
}

const resolved = computed(() => {
  const s = (props.status || '').toLowerCase()
  return STATUS_MAP[s] || { cls: 'badge-dim', key: '' }
})

const label = computed(() => {
  const s = (props.status || '').toLowerCase()
  if (resolved.value.key) {
    const key = resolved.value.key
    // Fall back to status string if the translation is missing.
    const translated = t(key)
    return translated && translated !== key ? translated : s
  }
  return s || '—'
})
</script>

<template>
  <span class="badge" :class="resolved.cls">{{ label }}</span>
</template>

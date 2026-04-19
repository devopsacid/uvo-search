<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const route = useRoute()

const navItems = [
  { key: 'nav.dashboard', path: '/', hk: 'D' },
  { key: 'nav.contracts', path: '/contracts', hk: 'C' },
  { key: 'nav.suppliers', path: '/suppliers', hk: 'S' },
  { key: 'nav.procurers', path: '/procurers', hk: 'P' },
  { key: 'nav.costs', path: '/costs', hk: 'X' },
  { key: 'nav.search', path: '/search', hk: '/' },
]

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <nav class="flex items-center gap-0 bg-ink-950 border-b border-ink-600 px-2 overflow-x-auto">
    <router-link
      v-for="item in navItems"
      :key="item.path"
      :to="item.path"
      class="flex items-baseline gap-2 px-4 py-2.5 text-xs uppercase tracking-wider text-fg-muted hover:text-fg-primary hover:bg-ink-800 border-b-2 border-transparent whitespace-nowrap"
      :class="{ '!text-accent !border-accent bg-ink-800': isActive(item.path) }"
    >
      <span>{{ t(item.key) }}</span>
      <span class="t-hotkey" data-testid="nav-hk">{{ item.hk }}</span>
    </router-link>
  </nav>
</template>

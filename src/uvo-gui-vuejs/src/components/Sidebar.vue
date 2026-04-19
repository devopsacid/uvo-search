<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from '../stores/theme'
import { useCommandPalette } from '../composables/useCommandPalette'

const { t } = useI18n()
const route = useRoute()
const theme = useThemeStore()
const palette = useCommandPalette()

const items = [
  { key: 'nav.dashboard', path: '/', icon: 'dashboard' },
  { key: 'nav.contracts', path: '/contracts', icon: 'contract' },
  { key: 'nav.suppliers', path: '/suppliers', icon: 'supplier' },
  { key: 'nav.procurers', path: '/procurers', icon: 'procurer' },
  { key: 'nav.costs', path: '/costs', icon: 'chart' },
  { key: 'nav.search', path: '/search', icon: 'search' },
]

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

const collapsed = ref(false)
onMounted(() => {
  try { collapsed.value = localStorage.getItem('uvo-admin-sidebar') === 'collapsed' } catch { /* ignore */ }
})
function toggleCollapse() {
  collapsed.value = !collapsed.value
  try { localStorage.setItem('uvo-admin-sidebar', collapsed.value ? 'collapsed' : 'expanded') } catch { /* ignore */ }
}
</script>

<template>
  <aside
    class="flex flex-col bg-l-panel dark:bg-d-panel border-r border-l-border dark:border-d-border transition-[width] duration-150"
    :class="collapsed ? 'w-[52px]' : 'w-[220px]'"
  >
    <div class="flex items-center justify-between h-12 px-3 border-b border-l-border dark:border-d-border">
      <router-link to="/" class="flex items-center gap-2 text-l-text dark:text-d-text font-semibold">
        <span class="inline-flex items-center justify-center w-7 h-7 rounded-sm bg-primary text-white text-xs font-bold">ÚVO</span>
        <span v-if="!collapsed" class="text-sm">Admin</span>
      </router-link>
    </div>

    <nav class="flex-1 py-2 overflow-y-auto">
      <router-link
        v-for="item in items"
        :key="item.path"
        :to="item.path"
        class="g-nav-link"
        :class="{ active: isActive(item.path) }"
      >
        <span class="inline-flex w-5 h-5 items-center justify-center" :title="t(item.key)">
          <svg v-if="item.icon === 'dashboard'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>
          <svg v-else-if="item.icon === 'contract'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 4h12l4 4v12H4z"/><path d="M16 4v4h4"/><path d="M7 13h10M7 17h8"/></svg>
          <svg v-else-if="item.icon === 'supplier'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 9v11h8V9"/><path d="M13 13v7h8V13"/><path d="M3 9l2-5h12l2 5"/></svg>
          <svg v-else-if="item.icon === 'procurer'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 21V10l8-6 8 6v11"/><path d="M10 21v-6h4v6"/></svg>
          <svg v-else-if="item.icon === 'chart'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20V6M4 20h16"/><path d="M8 20v-6M12 20v-10M16 20v-4M20 20v-8"/></svg>
          <svg v-else-if="item.icon === 'search'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        </span>
        <span v-if="!collapsed" class="truncate">{{ t(item.key) }}</span>
      </router-link>
    </nav>

    <div class="border-t border-l-border dark:border-d-border px-2 py-2 flex flex-col gap-1">
      <button class="g-nav-link" @click="palette.open()">
        <span class="inline-flex w-5 h-5 items-center justify-center">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 10h10M7 14h6"/></svg>
        </span>
        <span v-if="!collapsed" class="flex-1 truncate">{{ t('palette.title') }}</span>
        <span v-if="!collapsed" class="text-2xs dim border border-l-border dark:border-d-border px-1 rounded-sm">⌘K</span>
      </button>

      <button class="g-nav-link" @click="theme.toggle()">
        <span class="inline-flex w-5 h-5 items-center justify-center">
          <svg v-if="theme.mode === 'dark'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>
          <svg v-else class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
        </span>
        <span v-if="!collapsed" class="truncate">{{ t(theme.mode === 'dark' ? 'theme.light' : 'theme.dark') }}</span>
      </button>

      <button class="g-nav-link" @click="toggleCollapse" :title="collapsed ? t('nav.expand') : t('nav.collapse')">
        <span class="inline-flex w-5 h-5 items-center justify-center">
          <svg v-if="collapsed" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 6l6 6-6 6"/></svg>
          <svg v-else class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M15 6l-6 6 6 6"/></svg>
        </span>
        <span v-if="!collapsed" class="truncate">{{ t('nav.collapse') }}</span>
      </button>
    </div>
  </aside>
</template>

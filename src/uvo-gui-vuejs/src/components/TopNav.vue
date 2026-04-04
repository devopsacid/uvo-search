<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from '../stores/theme'
import { useFilterStore } from '../stores/filter'

const { t, locale } = useI18n()
const route = useRoute()
const theme = useThemeStore()
const filter = useFilterStore()

const navItems = [
  { key: 'nav.dashboard', path: '/' },
  { key: 'nav.contracts', path: '/contracts' },
  { key: 'nav.suppliers', path: '/suppliers' },
  { key: 'nav.procurers', path: '/procurers' },
  { key: 'nav.costs', path: '/costs' },
  { key: 'nav.search', path: '/search' },
]

function toggleLang() {
  locale.value = locale.value === 'sk' ? 'en' : 'sk'
}

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <nav class="bg-slate-800 text-white h-13 flex items-center px-6 gap-0 sticky top-0 z-50 shadow-md">
    <span class="font-bold text-base mr-8 tracking-tight">
      UVO <span class="text-sky-400">Admin</span>
    </span>

    <div class="flex items-center flex-1">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="px-3 h-13 flex items-center text-sm text-slate-400 hover:text-slate-200 border-b-2 border-transparent transition-colors"
        :class="{ 'text-white !border-sky-400': isActive(item.path) }"
      >
        {{ t(item.key) }}
      </router-link>
    </div>

    <div class="flex items-center gap-3 ml-auto">
      <span v-if="filter.isFiltered" class="text-xs text-sky-400 flex items-center gap-1">
        {{ filter.name }}
        <button @click="filter.clear()" class="ml-1 text-slate-400 hover:text-white">✕</button>
      </span>

      <button
        data-testid="lang-toggle"
        @click="toggleLang"
        class="bg-slate-700 text-slate-400 hover:text-white px-2.5 py-1 rounded text-xs transition-colors"
      >
        {{ locale === 'sk' ? 'EN' : 'SK' }}
      </button>

      <button
        @click="theme.toggle()"
        class="bg-slate-700 text-slate-400 hover:text-white px-2.5 py-1 rounded text-xs transition-colors"
      >
        {{ theme.isDark ? '☀️' : '🌙' }}
      </button>
    </div>
  </nav>
</template>

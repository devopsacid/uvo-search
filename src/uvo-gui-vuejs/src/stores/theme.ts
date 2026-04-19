import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

type Mode = 'light' | 'dark'
const KEY = 'uvo-admin-theme'

function initialMode(): Mode {
  if (typeof window === 'undefined') return 'light'
  const saved = localStorage.getItem(KEY) as Mode | null
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function apply(m: Mode) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', m === 'dark')
  try { localStorage.setItem(KEY, m) } catch { /* ignore */ }
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<Mode>(initialMode())
  apply(mode.value)

  watch(mode, (m) => apply(m), { flush: 'sync' })

  function toggle() {
    mode.value = mode.value === 'dark' ? 'light' : 'dark'
  }

  function set(m: Mode) {
    mode.value = m
  }

  return { mode, toggle, set }
})

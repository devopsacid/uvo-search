import { defineStore } from 'pinia'
import { ref, watchEffect } from 'vue'

type Mode = 'light' | 'dark'
const KEY = 'uvo-admin-theme'

function initialMode(): Mode {
  if (typeof window === 'undefined') return 'light'
  const saved = localStorage.getItem(KEY) as Mode | null
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<Mode>(initialMode())

  watchEffect(() => {
    if (typeof document === 'undefined') return
    document.documentElement.classList.toggle('dark', mode.value === 'dark')
    try { localStorage.setItem(KEY, mode.value) } catch { /* ignore */ }
  })

  function toggle() {
    mode.value = mode.value === 'dark' ? 'light' : 'dark'
  }

  function set(m: Mode) {
    mode.value = m
  }

  return { mode, toggle, set }
})

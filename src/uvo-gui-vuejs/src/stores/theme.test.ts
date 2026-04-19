import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useThemeStore } from './theme'

describe('useThemeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('toggles light ↔ dark', () => {
    const s = useThemeStore()
    const initial = s.mode
    s.toggle()
    expect(s.mode).not.toBe(initial)
    s.toggle()
    expect(s.mode).toBe(initial)
  })

  it('persists mode to localStorage', () => {
    const s = useThemeStore()
    s.set('dark')
    expect(localStorage.getItem('uvo-admin-theme')).toBe('dark')
    s.set('light')
    expect(localStorage.getItem('uvo-admin-theme')).toBe('light')
  })

  it('applies dark class on html when mode is dark', () => {
    const s = useThemeStore()
    s.set('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    s.set('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})

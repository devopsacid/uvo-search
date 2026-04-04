import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useThemeStore } from './theme'

describe('useThemeStore', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts in light mode', () => {
    const store = useThemeStore()
    expect(store.isDark).toBe(false)
  })

  it('toggles to dark mode', () => {
    const store = useThemeStore()
    store.toggle()
    expect(store.isDark).toBe(true)
  })
})

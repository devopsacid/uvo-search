import { describe, it, expect, beforeEach } from 'vitest'
import { useCommandPalette } from './useCommandPalette'

describe('useCommandPalette', () => {
  beforeEach(() => {
    const p = useCommandPalette()
    p.close()
  })

  it('starts closed', () => {
    const p = useCommandPalette()
    expect(p.isOpen.value).toBe(false)
  })

  it('opens and closes', () => {
    const p = useCommandPalette()
    p.open()
    expect(p.isOpen.value).toBe(true)
    p.close()
    expect(p.isOpen.value).toBe(false)
  })

  it('toggle flips state', () => {
    const p = useCommandPalette()
    p.toggle()
    expect(p.isOpen.value).toBe(true)
    p.toggle()
    expect(p.isOpen.value).toBe(false)
  })

  it('shares state across calls (singleton)', () => {
    const a = useCommandPalette()
    const b = useCommandPalette()
    a.open()
    expect(b.isOpen.value).toBe(true)
  })
})

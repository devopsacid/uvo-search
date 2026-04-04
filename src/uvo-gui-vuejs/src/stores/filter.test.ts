import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useFilterStore } from './filter'

describe('useFilterStore', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts with no company selected', () => {
    const store = useFilterStore()
    expect(store.ico).toBeNull()
    expect(store.isFiltered).toBe(false)
  })

  it('sets company filter', () => {
    const store = useFilterStore()
    store.setCompany({ ico: '12345678', name: 'Ministry', type: 'procurer' })
    expect(store.ico).toBe('12345678')
    expect(store.isFiltered).toBe(true)
  })

  it('clears company filter', () => {
    const store = useFilterStore()
    store.setCompany({ ico: '12345678', name: 'Ministry', type: 'procurer' })
    store.clear()
    expect(store.ico).toBeNull()
    expect(store.isFiltered).toBe(false)
  })

  it('provides query params for API calls', () => {
    const store = useFilterStore()
    store.setCompany({ ico: '12345678', name: 'Ministry', type: 'procurer' })
    expect(store.queryParams).toEqual({ ico: '12345678', entity_type: 'procurer' })
  })
})

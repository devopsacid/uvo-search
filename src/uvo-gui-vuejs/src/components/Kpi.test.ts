import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Kpi from './Kpi.vue'

describe('Kpi', () => {
  it('renders label, value and delta', () => {
    const w = mount(Kpi, {
      props: { label: 'Total', value: '€4.8B', delta: '+8.4%', deltaDir: 'up' },
    })
    expect(w.text()).toContain('Total')
    expect(w.text()).toContain('€4.8B')
    expect(w.text()).toContain('+8.4%')
  })

  it('applies up class for positive delta', () => {
    const w = mount(Kpi, {
      props: { label: 'Total', value: '1', delta: '+1%', deltaDir: 'up' },
    })
    expect(w.html()).toContain('text-up')
  })

  it('applies down class for negative delta', () => {
    const w = mount(Kpi, {
      props: { label: 'Total', value: '1', delta: '-1%', deltaDir: 'down' },
    })
    expect(w.html()).toContain('text-down')
  })
})

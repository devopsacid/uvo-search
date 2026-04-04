import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import KpiCard from './KpiCard.vue'

describe('KpiCard', () => {
  it('renders label and value', () => {
    const w = mount(KpiCard, { props: { label: 'Total', value: '€ 4.2B', color: 'blue' } })
    expect(w.text()).toContain('Total')
    expect(w.text()).toContain('€ 4.2B')
  })

  it('renders delta when provided', () => {
    const w = mount(KpiCard, { props: { label: 'Total', value: '€ 4.2B', color: 'blue', delta: '↑ +8%' } })
    expect(w.text()).toContain('↑ +8%')
  })

  it('applies correct border color class for blue', () => {
    const w = mount(KpiCard, { props: { label: 'Total', value: '€ 4.2B', color: 'blue' } })
    expect(w.html()).toContain('border-blue-600')
  })
})

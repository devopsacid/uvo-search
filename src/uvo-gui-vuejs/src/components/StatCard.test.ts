import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import StatCard from './StatCard.vue'

describe('StatCard', () => {
  it('renders label and value', () => {
    const w = mount(StatCard, { props: { label: 'Total', value: '€4.8B' } })
    expect(w.text()).toContain('Total')
    expect(w.text()).toContain('€4.8B')
  })

  it('colors delta as good when direction is up', () => {
    const w = mount(StatCard, {
      props: { label: 'Total', value: '1', delta: '+8.4%', deltaDir: 'up' },
    })
    expect(w.html()).toContain('text-good')
    expect(w.text()).toContain('+8.4%')
  })

  it('colors delta as bad when direction is down', () => {
    const w = mount(StatCard, {
      props: { label: 'Total', value: '1', delta: '-2%', deltaDir: 'down' },
    })
    expect(w.html()).toContain('text-bad')
  })
})

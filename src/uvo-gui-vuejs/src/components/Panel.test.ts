import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Panel from './Panel.vue'

describe('Panel', () => {
  it('renders title and body slot', () => {
    const w = mount(Panel, {
      props: { title: 'Top Suppliers' },
      slots: { default: '<p>body</p>' },
    })
    expect(w.text()).toContain('Top Suppliers')
    expect(w.text()).toContain('body')
  })

  it('shows loading indicator when loading', () => {
    const w = mount(Panel, {
      props: { title: 'X', loading: true },
    })
    expect(w.text()).toContain('loading')
  })
})

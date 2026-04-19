import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Panel from './Panel.vue'

describe('Panel', () => {
  it('renders uppercase title with terminal prefix', () => {
    const w = mount(Panel, {
      props: { title: 'Top Suppliers' },
      slots: { default: '<p>body</p>' },
    })
    expect(w.text()).toContain('> Top Suppliers')
    expect(w.text()).toContain('body')
  })
})

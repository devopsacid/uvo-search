import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { describe, it, expect, beforeEach } from 'vitest'
import Sidebar from './Sidebar.vue'
import sk from '../i18n/sk'
import en from '../i18n/en'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/:p(.*)*', component: { template: '<div/>' } },
  ],
})
const i18n = createI18n({ legacy: false, locale: 'sk', messages: { sk, en } })

function mountSidebar() {
  return mount(Sidebar, {
    global: { plugins: [router, i18n] },
  })
}

describe('Sidebar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders all main nav links', () => {
    const w = mountSidebar()
    const text = w.text()
    expect(text).toContain('Dashboard')
    expect(text).toContain('Zákazky')
    expect(text).toContain('Dodávatelia')
    expect(text).toContain('Obstarávatelia')
  })

  it('renders theme toggle and palette button', () => {
    const w = mountSidebar()
    const text = w.text()
    expect(text.toLowerCase()).toContain('mode')
    expect(text).toContain('⌘K')
  })
})

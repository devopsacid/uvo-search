import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { describe, it, expect } from 'vitest'
import TopNav from './TopNav.vue'
import sk from '../i18n/sk'
import en from '../i18n/en'

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/:p(.*)*', component: { template: '<div/>' } }],
})
const i18n = createI18n({ legacy: false, locale: 'sk', messages: { sk, en } })

function mountNav() {
  return mount(TopNav, {
    global: { plugins: [createPinia(), router, i18n] },
  })
}

describe('TopNav', () => {
  it('renders all main nav items', () => {
    const w = mountNav()
    expect(w.text()).toContain('Dashboard')
    expect(w.text()).toContain('Zákazky')
    expect(w.text()).toContain('Dodávatelia')
    expect(w.text()).toContain('Obstarávatelia')
  })

  it('renders hotkey hints', () => {
    const w = mountNav()
    const hks = w.findAll('[data-testid="nav-hk"]').map(el => el.text())
    expect(hks).toContain('D')
    expect(hks).toContain('C')
    expect(hks).toContain('S')
  })
})

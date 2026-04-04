import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, it, expect } from 'vitest'
import ContractTable from './ContractTable.vue'
import sk from '../i18n/sk'
import en from '../i18n/en'

const i18n = createI18n({ legacy: false, locale: 'sk', messages: { sk, en } })

const rows = [
  { id: '1', title: 'IT Project', procurer_name: 'MF SR', procurer_ico: '123', supplier_name: 'Tech', supplier_ico: '456', value: 500000, cpv_code: '72000000', year: 2024, status: 'active' },
]

describe('ContractTable', () => {
  it('renders contract rows', () => {
    const w = mount(ContractTable, {
      props: { rows, total: 1, offset: 0, limit: 20 },
      global: { plugins: [i18n] },
    })
    expect(w.text()).toContain('IT Project')
    expect(w.text()).toContain('MF SR')
  })

  it('emits select when row clicked', async () => {
    const w = mount(ContractTable, {
      props: { rows, total: 1, offset: 0, limit: 20 },
      global: { plugins: [i18n] },
    })
    await w.find('tr.cursor-pointer').trigger('click')
    expect(w.emitted('select')?.[0][0]).toEqual(rows[0])
  })
})

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { App } from '../App'
import sk from '../i18n/sk'

// Stub fetch so TanStack Query doesn't error on missing API
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: async () => ({
    total_value: 1000000,
    contract_count: 42,
    avg_value: 23809,
    active_suppliers: 15,
    deltas: {},
  }),
} as Response)

describe('App', () => {
  it('renders the Slovak navigation label for overview', async () => {
    render(<App />)
    const navItem = await screen.findByText(sk.nav.overview)
    expect(navItem).toBeInTheDocument()
  })

  it('renders the Slovak navigation label for about', async () => {
    render(<App />)
    const navItem = await screen.findByText(sk.nav.about)
    expect(navItem).toBeInTheDocument()
  })
})

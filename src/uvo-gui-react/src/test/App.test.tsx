import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { App } from '../App'
import sk from '../i18n/sk'

// Stub fetch so TanStack Query doesn't error on missing API.
// Returns type-appropriate shapes based on URL to avoid runtime crashes
// in page components (e.g. recent?.map requires an array).
global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  let body: unknown
  if (url.includes('/dashboard/recent')) {
    body = []
  } else if (url.includes('/dashboard/spend-by-year') || url.includes('/dashboard/top-suppliers') || url.includes('/dashboard/top-procurers') || url.includes('/dashboard/by-cpv') || url.includes('/dashboard/by-month')) {
    body = []
  } else {
    body = { total_value: 1000000, contract_count: 42, avg_value: 23809, active_suppliers: 15, deltas: {} }
  }
  return { ok: true, json: async () => body } as Response
}) as typeof fetch

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

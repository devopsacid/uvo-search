import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { App } from '../App'
import sk from '../i18n/sk'

// Stub fetch globally — returns type-appropriate shapes per URL so page
// components don't crash (e.g. recent?.map requires an array).
global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  let body: unknown
  if (url.includes('/recent') || url.includes('/spend-by-year') || url.includes('/top-suppliers') || url.includes('/top-procurers') || url.includes('/by-cpv') || url.includes('/by-month')) {
    body = []
  } else {
    body = { total_value: 1000000, contract_count: 42, avg_value: 23809, active_suppliers: 15, deltas: {} }
  }
  return { ok: true, json: async () => body } as Response
}) as typeof fetch

describe('Layout + Routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function renderApp() {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: Infinity,
        },
      },
    })
    return render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    )
  }

  it('renders Slovak navigation labels correctly', async () => {
    renderApp()

    expect(await screen.findByText(sk.nav.overview)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.firmy)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.zakazky)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.about)).toBeInTheDocument()
  })

  it('renders nav items with correct href', async () => {
    renderApp()

    const overviewLink = await screen.findByRole('link', { name: sk.nav.overview })
    expect(overviewLink).toHaveAttribute('href', '/')

    const firmyLink = await screen.findByRole('link', { name: sk.nav.firmy })
    expect(firmyLink).toHaveAttribute('href', '/firmy')

    const zakazkyLink = await screen.findByRole('link', { name: sk.nav.zakazky })
    expect(zakazkyLink).toHaveAttribute('href', '/zakazky')

    const aboutLink = await screen.findByRole('link', { name: sk.nav.about })
    expect(aboutLink).toHaveAttribute('href', '/about')
  })

  it('has main content area', async () => {
    renderApp()

    const main = screen.getByRole('main')
    expect(main).toBeInTheDocument()
  })

  it('displays overview page as default route', async () => {
    renderApp()

    expect(await screen.findByText(sk.overview.title)).toBeInTheDocument()
  })

  it('renders UVO branding text', async () => {
    renderApp()
    expect(await screen.findByText('UVO')).toBeInTheDocument()
  })

  it('has nav aria-label', async () => {
    renderApp()
    const nav = screen.getByLabelText('Hlavna navigacia')
    expect(nav).toBeInTheDocument()
  })
})

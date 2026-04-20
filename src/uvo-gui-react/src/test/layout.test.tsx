import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { App } from '../App'
import sk from '../i18n/sk'

// Stub fetch globally
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
    expect(await screen.findByText(sk.nav.search)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.suppliers)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.procurers)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.about)).toBeInTheDocument()
  })

  it('renders nav items with correct href', async () => {
    renderApp()

    const overviewLink = await screen.findByRole('link', { name: sk.nav.overview })
    expect(overviewLink).toHaveAttribute('href', '/')

    const searchLink = await screen.findByRole('link', { name: sk.nav.search })
    expect(searchLink).toHaveAttribute('href', '/search')

    const suppliersLink = await screen.findByRole('link', { name: sk.nav.suppliers })
    expect(suppliersLink).toHaveAttribute('href', '/suppliers')

    const procurersLink = await screen.findByRole('link', { name: sk.nav.procurers })
    expect(procurersLink).toHaveAttribute('href', '/procurers')

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

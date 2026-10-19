import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { App } from '../App'
import sk from '../i18n/sk'
import { makeAnalyticsFetch } from './fixtures/analytics'

// Stub fetch globally; analytics endpoints return fixtures so the default route renders.
global.fetch = makeAnalyticsFetch().impl

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

    expect(await screen.findByText(sk.nav.analytics)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.firmy)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.zakazky)).toBeInTheDocument()
    expect(await screen.findByText(sk.nav.about)).toBeInTheDocument()
  })

  it('renders nav items with correct href', async () => {
    renderApp()

    const analyticsLink = await screen.findByRole('link', { name: sk.nav.analytics })
    expect(analyticsLink).toHaveAttribute('href', '/analytika')

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

  it('redirects the default route to the analytics overview', async () => {
    renderApp()

    expect(await screen.findByRole('heading', { level: 1, name: sk.analytics.title })).toBeInTheDocument()
  })

  it('renders UVO branding text', async () => {
    renderApp()
    expect(await screen.findByText('UVO')).toBeInTheDocument()
  })

  it('has nav aria-label', async () => {
    renderApp()
    const nav = screen.getByLabelText('Hlavná navigácia')
    expect(nav).toBeInTheDocument()
  })
})

describe('Header small screens', () => {
  it('lets the nav scroll inside itself instead of widening the page', async () => {
    const { Header } = await import('../components/layout/Header')
    const { renderWithProviders } = await import('./utils')
    renderWithProviders(<Header />)
    const nav = screen.getByRole('navigation', { name: sk.common.mainNavLabel })
    expect(nav.className).toContain('overflow-x-auto')
    expect(nav.className).toContain('max-w-full')
    expect(nav.parentElement?.className).toContain('flex-wrap')
  })
})

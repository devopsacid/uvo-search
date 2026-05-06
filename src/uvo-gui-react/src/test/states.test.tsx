import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderWithProviders, screen, waitFor } from './utils'
import { SearchPage } from '../pages/SearchPage'
import sk from '../i18n/sk'

describe('Loading + Empty + Error States', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('Loading states', () => {
    it('shows skeleton rows while contracts are loading', async () => {
      global.fetch = vi.fn(async (): Promise<Response> => new Promise(() => {})) as typeof fetch

      renderWithProviders(<SearchPage />, { route: '/search?q=test' })

      await waitFor(() => {
        const skeletons = screen.getAllByTestId('skeleton-row')
        expect(skeletons.length).toBeGreaterThan(0)
      }, { timeout: 2000 })
    })

    it('shows skeleton loading state for contract detail pane', async () => {
      global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
        if (url.includes('/contracts/')) {
          return new Promise(() => {}) // detail endpoint never resolves -> loading state
        }
        return {
          ok: true,
          json: async () => ({
            data: [
              {
                id: '1',
                title: 'Test',
                procurer_ico: '11111111',
                procurer_name: 'Proc',
                supplier_ico: '22222222',
                supplier_name: 'Supp',
                value: 1000,
                year: 2024,
                status: 'completed',
                cpv_code: null,
              },
            ],
            pagination: { total: 1, limit: 20, offset: 0 },
          }),
        } as Response
      }) as typeof fetch

      renderWithProviders(<SearchPage />, { route: '/search' })

      const firstRow = await screen.findByText('Test')
      firstRow.parentElement?.parentElement?.click()

      await waitFor(() => {
        const skeletons = screen.getAllByTestId('skeleton')
        expect(skeletons.length).toBeGreaterThan(0)
      }, { timeout: 2000 })
    })
  })

  describe('Empty states', () => {
    beforeEach(() => {
      global.fetch = vi.fn(async (): Promise<Response> => {
        return {
          ok: true,
          json: async () => ({
            data: [],
            pagination: { total: 0, limit: 20, offset: 0 },
          }),
        } as Response
      }) as typeof fetch
    })

    it('shows empty state title for contracts with no results', async () => {
      renderWithProviders(<SearchPage />, { route: '/search?q=nonexistent' })

      await waitFor(() => {
        expect(screen.getByText(sk.search.noResults)).toBeInTheDocument()
      })
    })

    it('shows empty state description for contracts', async () => {
      renderWithProviders(<SearchPage />, { route: '/search?q=nonexistent' })

      await waitFor(() => {
        expect(screen.getByText(sk.search.noResultsHint)).toBeInTheDocument()
      })
    })

    it('shows clear filters action button in empty state when filters exist', async () => {
      renderWithProviders(<SearchPage />, { route: '/search?q=test' })

      await waitFor(() => {
        const clearButton = screen.getByRole('button', { name: sk.common.clearFilters })
        expect(clearButton).toBeInTheDocument()
      })
    })

    it('does not show clear filters action when no filters are applied', async () => {
      renderWithProviders(<SearchPage />, { route: '/search' })

      // Wait for empty state to load (no filters → empty results but no clearFilters button)
      await waitFor(() => {
        expect(screen.getByText(sk.search.noResults)).toBeInTheDocument()
      })

      const clearButton = screen.queryByRole('button', { name: sk.common.clearFilters })
      expect(clearButton).not.toBeInTheDocument()
    })

  })

  describe('Error states', () => {
    beforeEach(() => {
      global.fetch = vi.fn(async (): Promise<Response> => {
        return {
          ok: false,
          status: 500,
          json: async () => ({ message: 'Internal server error' }),
        } as Response
      }) as typeof fetch
    })

    it('shows error message when search fails', async () => {
      renderWithProviders(<SearchPage />, { route: '/search?q=test' })

      await waitFor(() => {
        expect(screen.getByText(new RegExp(sk.common.error))).toBeInTheDocument()
      })
    })

  })


  describe('No scroll layout shift', () => {
    it('maintains table header while loading results', async () => {
      global.fetch = vi.fn(async (): Promise<Response> => new Promise(() => {})) as typeof fetch

      renderWithProviders(<SearchPage />, { route: '/search?q=test' })

      const headers = screen.getAllByRole('columnheader')
      expect(headers.length).toBeGreaterThan(0)

      // Headers should remain visible during skeleton loading
      await waitFor(() => {
        expect(screen.getByText(sk.search.colTitle)).toBeInTheDocument()
      }, { timeout: 2000 })
    })
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor } from './utils'
import { SearchPage } from '../pages/SearchPage'
import { SuppliersPage } from '../pages/SuppliersPage'
import { ProcurersPage } from '../pages/ProcurersPage'
import sk from '../i18n/sk'

describe('Loading + Empty + Error States', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Loading states', () => {
    it('shows skeleton rows while contracts are loading', async () => {
      global.fetch = vi.fn(() => new Promise(() => {})) // Never resolves

      renderWithProviders(<SearchPage />, { route: '/search?q=test' })

      await waitFor(() => {
        const skeletons = screen.getAllByTestId('skeleton-row')
        expect(skeletons.length).toBeGreaterThan(0)
      }, { timeout: 2000 })
    })

    it('shows skeleton rows while suppliers are loading', async () => {
      global.fetch = vi.fn(() => new Promise(() => {})) // Never resolves

      renderWithProviders(<SuppliersPage />, { route: '/suppliers?q=test' })

      await waitFor(() => {
        const skeletons = screen.getAllByTestId('skeleton-row')
        expect(skeletons.length).toBeGreaterThan(0)
      }, { timeout: 2000 })
    })

    it('shows skeleton loading state for contract detail pane', async () => {
      vi.useFakeTimers()
      global.fetch = vi.fn((url: string) => {
        if (url.includes('/contracts/')) {
          return new Promise(() => {})
        }
        return Promise.resolve({
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
        } as Response)
      })

      renderWithProviders(<SearchPage />, { route: '/search' })

      const firstRow = await screen.findByText('Test')
      firstRow.parentElement?.parentElement?.click()

      await waitFor(() => {
        const skeletons = screen.getAllByTestId('skeleton')
        expect(skeletons.length).toBeGreaterThan(0)
      }, { timeout: 1000 })

      vi.useRealTimers()
    })
  })

  describe('Empty states', () => {
    beforeEach(() => {
      global.fetch = vi.fn((url: string) => {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            data: [],
            pagination: { total: 0, limit: 20, offset: 0 },
          }),
        } as Response)
      })
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

      // Wait for empty state to load
      await waitFor(() => {
        expect(screen.getByText(sk.search.selectRow)).toBeInTheDocument()
      })

      const clearButton = screen.queryByRole('button', { name: sk.common.clearFilters })
      expect(clearButton).not.toBeInTheDocument()
    })

    it('shows empty state for suppliers with no results', async () => {
      renderWithProviders(<SuppliersPage />, { route: '/suppliers?q=nonexistent' })

      await waitFor(() => {
        expect(screen.getByText(sk.suppliers.noResults)).toBeInTheDocument()
        expect(screen.getByText(sk.suppliers.noResultsHint)).toBeInTheDocument()
      })
    })

    it('shows empty state for procurers with no results', async () => {
      renderWithProviders(<ProcurersPage />, { route: '/procurers?q=nonexistent' })

      await waitFor(() => {
        expect(screen.getByText(sk.procurers.noResults)).toBeInTheDocument()
        expect(screen.getByText(sk.procurers.noResultsHint)).toBeInTheDocument()
      })
    })
  })

  describe('Error states', () => {
    beforeEach(() => {
      global.fetch = vi.fn((url: string) => {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: async () => ({ message: 'Internal server error' }),
        } as Response)
      })
    })

    it('shows error message when search fails', async () => {
      renderWithProviders(<SearchPage />, { route: '/search?q=test' })

      await waitFor(() => {
        expect(screen.getByText(new RegExp(sk.common.error))).toBeInTheDocument()
      })
    })

    it('shows error message when suppliers fetch fails', async () => {
      renderWithProviders(<SuppliersPage />, { route: '/suppliers' })

      await waitFor(() => {
        expect(screen.getByText(sk.common.error)).toBeInTheDocument()
      })
    })

    it('shows error message when procurers fetch fails', async () => {
      renderWithProviders(<ProcurersPage />, { route: '/procurers' })

      await waitFor(() => {
        expect(screen.getByText(sk.common.error)).toBeInTheDocument()
      })
    })
  })


  describe('No scroll layout shift', () => {
    it('maintains table header while loading results', async () => {
      global.fetch = vi.fn(() => new Promise(() => {}))

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

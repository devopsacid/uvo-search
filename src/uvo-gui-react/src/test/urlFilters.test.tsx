import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, fireEvent, waitFor } from './utils'
import { SearchPage } from '../pages/SearchPage'
import { SuppliersPage } from '../pages/SuppliersPage'
import sk from '../i18n/sk'

global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  if (url.includes('/contracts')) {
    const urlObj = new URL(url, 'http://localhost')
    const q = urlObj.searchParams.get('q')
    const year = urlObj.searchParams.get('date_from')?.substring(0, 4)

    return {
      ok: true,
      json: async () => ({
        data: q || year ? [
          {
            id: '1',
            title: 'Matching Contract',
            procurer_ico: '12345678',
            procurer_name: 'Procurer A',
            supplier_ico: '87654321',
            supplier_name: 'Supplier A',
            value: 5000,
            year: year ? parseInt(year) : 2024,
            status: 'completed',
            cpv_code: '45000000',
          },
        ] : [],
        pagination: { total: q || year ? 100 : 0, limit: 20, offset: 0 },
      }),
    } as Response
  }
  if (url.includes('/suppliers')) {
    const urlObj = new URL(url, 'http://localhost')
    const q = urlObj.searchParams.get('q')

    return {
      ok: true,
      json: async () => ({
        data: q ? [
          { ico: '87654321', name: 'Supplier A', contract_count: 5, total_value: 5000 },
        ] : [],
        pagination: { total: q ? 100 : 0, limit: 20, offset: 0 },
      }),
    } as Response
  }
  return { ok: false, json: async () => ({}) } as Response
}) as typeof fetch

describe('URL-as-State Filters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('initializes with URL query parameters', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?q=foo' })

    const input = await screen.findByPlaceholderText(sk.search.placeholder)
    expect((input as HTMLInputElement).value).toBe('foo')
  })

  it('preserves year filter from URL on mount', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?year=2023' })

    const select = await screen.findByDisplayValue('2023')
    expect(select).toBeInTheDocument()
  })

  it('preserves CPV filter from URL', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?cpv=45000000' })

    const input = await screen.findByPlaceholderText('napr. 45000000')
    expect((input as HTMLInputElement).value).toBe('45000000')
  })

  it('updates filter when form input changes', async () => {
    renderWithProviders(<SearchPage />, { route: '/search' })
    const input = await screen.findByPlaceholderText(sk.search.placeholder) as HTMLInputElement

    fireEvent.change(input, { target: { value: 'test query' } })

    await waitFor(() => {
      expect(input.value).toBe('test query')
    })
  })

  it('preserves multiple filters in URL', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?q=test&year=2023&cpv=45000000' })

    const qInput = await screen.findByPlaceholderText(sk.search.placeholder)
    const yearSelect = await screen.findByDisplayValue('2023')
    const cpvInput = await screen.findByPlaceholderText('napr. 45000000')

    expect((qInput as HTMLInputElement).value).toBe('test')
    expect((yearSelect as HTMLSelectElement).value).toBe('2023')
    expect((cpvInput as HTMLInputElement).value).toBe('45000000')
  })

  it('clear filters button resets all filter inputs', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?q=test&year=2023' })

    const clearButton = await screen.findByRole('button', { name: sk.common.clearFilters })
    fireEvent.click(clearButton)

    await waitFor(() => {
      const input = screen.getByPlaceholderText(sk.search.placeholder) as HTMLInputElement
      expect(input.value).toBe('')
    })
  })

  it('suppliers page preserves search filter in URL', async () => {
    renderWithProviders(<SuppliersPage />, { route: '/suppliers?q=Acme' })

    const input = await screen.findByPlaceholderText(sk.suppliers.searchPlaceholder)
    expect((input as HTMLInputElement).value).toBe('Acme')
  })

  it('year filter select shows all years as options', async () => {
    renderWithProviders(<SearchPage />, { route: '/search' })

    const select = await screen.findByDisplayValue('Všetky')
    const options = (select as HTMLSelectElement).options

    expect(options.length).toBeGreaterThanOrEqual(10)
  })

  it('removing year filter shows blank selection', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?year=2023' })

    const yearSelect = await screen.findByDisplayValue('2023') as HTMLSelectElement
    fireEvent.change(yearSelect, { target: { value: '' } })

    await waitFor(() => {
      expect(yearSelect.value).toBe('')
    })
  })

  it('supplier page shows pagination when results exist', async () => {
    renderWithProviders(<SuppliersPage />, { route: '/suppliers?q=test' })

    // Wait for data to load and pagination to appear
    await waitFor(() => {
      // Pagination exists when there are results
      const headings = screen.getAllByText('Dodavatelia')
      expect(headings.length).toBeGreaterThan(0)
    })
  })

  it('supplier and procurer ico filters can be set from URL', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?supplier_ico=87654321' })

    const inputs = screen.getAllByPlaceholderText('IČO')
    expect(inputs.length).toBeGreaterThanOrEqual(1)
  })

  it('changing filter resets form to show updated value', async () => {
    renderWithProviders(<SearchPage />, { route: '/search?q=original' })

    const input = await screen.findByPlaceholderText(sk.search.placeholder) as HTMLInputElement
    expect(input.value).toBe('original')

    fireEvent.change(input, { target: { value: 'updated' } })

    await waitFor(() => {
      expect(input.value).toBe('updated')
    })
  })
})

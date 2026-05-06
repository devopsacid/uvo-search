import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor } from './utils'
import { SupplierDetailPage } from '../pages/SupplierDetailPage'
import { ProcurerDetailPage } from '../pages/ProcurerDetailPage'
import sk from '../i18n/sk'

describe('Detail Pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('SupplierDetailPage', () => {
    beforeEach(() => {
      global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
        if (url.includes('/suppliers/87654321/summary')) {
          return {
            ok: true,
            json: async () => ({
              ico: '87654321',
              name: 'Supplier A',
              contract_count: 25,
              total_value: 50000,
              avg_value: 2000,
              spend_by_year: [
                { year: 2022, total_value: 10000 },
                { year: 2023, total_value: 15000 },
                { year: 2024, total_value: 25000 },
              ],
            }),
          } as Response
        }
        if (url.includes('/suppliers/87654321')) {
          return {
            ok: true,
            json: async () => ({
              ico: '87654321',
              name: 'Supplier A',
              contract_count: 25,
              total_value: 50000,
              avg_value: 2000,
              years_active: [2022, 2023, 2024],
              top_procurers: [
                { ico: '11111111', name: 'Procurer X', contract_count: 10, total_value: 20000 },
                { ico: '22222222', name: 'Procurer Y', contract_count: 8, total_value: 15000 },
                { ico: '33333333', name: 'Procurer Z', contract_count: 7, total_value: 15000 },
              ],
              contracts: [
                {
                  id: '1',
                  title: 'Contract 1',
                  procurer_ico: '11111111',
                  procurer_name: 'Procurer X',
                  supplier_ico: '87654321',
                  supplier_name: 'Supplier A',
                  value: 5000,
                  year: 2024,
                  status: 'completed',
                  cpv_code: '45000000',
                },
              ],
            }),
          } as Response
        }
        return { ok: false, json: async () => ({}) } as Response
      }) as typeof fetch
    })

    it('renders supplier name and ICO', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getByText('Supplier A')).toBeInTheDocument()
        expect(screen.getByText(/87654321/)).toBeInTheDocument()
      })
    })

    it('renders years active', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(/2022–2024/)).toBeInTheDocument()
      })
    })

    it('displays KPI cards: contracts, total volume, average value', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getAllByText(sk.suppliers.kpiContracts).length).toBeGreaterThan(0)
        expect(screen.getAllByText(sk.suppliers.kpiTotal).length).toBeGreaterThan(0)
        expect(screen.getAllByText(sk.suppliers.kpiAvg).length).toBeGreaterThan(0)
      })
    })

    it('displays formatted currency values in KPIs', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        const kpiValues = screen.getAllByText(/€|,/)
        expect(kpiValues.length).toBeGreaterThan(0)
      })
    })

    it('renders spend-by-year chart section', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(sk.suppliers.sectionSpend)).toBeInTheDocument()
      })
    })

    it('renders top procurers table', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(sk.suppliers.sectionProcurers)).toBeInTheDocument()
        expect(screen.getAllByText('Procurer X').length).toBeGreaterThan(0)
        expect(screen.getAllByText('Procurer Y').length).toBeGreaterThan(0)
      })
    })

    it('renders top procurers as links', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        const procurerLinks = screen.getAllByRole('link', { name: 'Procurer X' })
        expect(procurerLinks.length).toBeGreaterThan(0)
        expect(procurerLinks[0]).toHaveAttribute('href', '/firma/11111111')
      })
    })

    it('renders contracts table', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getAllByText(sk.suppliers.sectionContracts).length).toBeGreaterThan(0)
        expect(screen.getByText('Contract 1')).toBeInTheDocument()
      })
    })

    it('displays contract procurer as link', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        const procurerLinks = screen.getAllByRole('link', { name: 'Procurer X' })
        expect(procurerLinks.length).toBeGreaterThan(0)
        expect(procurerLinks[0]).toHaveAttribute('href', '/firma/11111111')
      })
    })

    it('has back link to suppliers list', async () => {
      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        const backLink = screen.getByRole('link', { name: /Spat/ })
        expect(backLink).toHaveAttribute('href', '/firmy')
      })
    })

    it('shows loading skeletons while data is loading', async () => {
      global.fetch = vi.fn(async (): Promise<Response> => new Promise(() => {})) as typeof fetch

      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        const skeletons = screen.getAllByTestId('skeleton')
        expect(skeletons.length).toBeGreaterThan(0)
      })
    })

    it('shows error message when fetch fails', async () => {
      global.fetch = vi.fn(async (): Promise<Response> => ({
        ok: false,
        status: 404,
        json: async () => ({ message: 'Not found' }),
      } as Response)) as typeof fetch

      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(sk.common.error)).toBeInTheDocument()
        expect(screen.getByRole('link', { name: /Spat/ })).toBeInTheDocument()
      })
    })
  })

  describe('ProcurerDetailPage', () => {
    beforeEach(() => {
      global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
        if (url.includes('/procurers/12345678/summary')) {
          return {
            ok: true,
            json: async () => ({
              ico: '12345678',
              name: 'Procurer A',
              contract_count: 50,
              total_spend: 100000,
              avg_value: 2000,
              spend_by_year: [
                { year: 2022, total_value: 20000 },
                { year: 2023, total_value: 30000 },
                { year: 2024, total_value: 50000 },
              ],
            }),
          } as Response
        }
        if (url.includes('/procurers/12345678')) {
          return {
            ok: true,
            json: async () => ({
              ico: '12345678',
              name: 'Procurer A',
              contract_count: 50,
              total_spend: 100000,
              avg_value: 2000,
              years_active: [2022, 2023, 2024],
              top_suppliers: [
                { ico: '87654321', name: 'Supplier A', contract_count: 15, total_value: 30000 },
                { ico: '76543210', name: 'Supplier B', contract_count: 12, total_value: 25000 },
                { ico: '65432109', name: 'Supplier C', contract_count: 10, total_value: 20000 },
              ],
              contracts: [
                {
                  id: '1',
                  title: 'Contract 1',
                  procurer_ico: '12345678',
                  procurer_name: 'Procurer A',
                  supplier_ico: '87654321',
                  supplier_name: 'Supplier A',
                  value: 5000,
                  year: 2024,
                  status: 'completed',
                  cpv_code: '45000000',
                },
              ],
            }),
          } as Response
        }
        return { ok: false, json: async () => ({}) } as Response
      }) as typeof fetch
    })

    it('renders procurer name and ICO', async () => {
      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        expect(screen.getByText('Procurer A')).toBeInTheDocument()
        expect(screen.getByText(/12345678/)).toBeInTheDocument()
      })
    })

    it('displays KPI cards: contracts, total spend, average value', async () => {
      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        expect(screen.getAllByText(sk.procurers.kpiContracts).length).toBeGreaterThan(0)
        expect(screen.getAllByText(sk.procurers.kpiTotal).length).toBeGreaterThan(0)
        expect(screen.getAllByText(sk.procurers.kpiAvg).length).toBeGreaterThan(0)
      })
    })

    it('renders spend-by-year chart section', async () => {
      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(sk.procurers.sectionSpend)).toBeInTheDocument()
      })
    })

    it('renders top suppliers table', async () => {
      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(sk.procurers.sectionSuppliers)).toBeInTheDocument()
        expect(screen.getAllByText('Supplier A').length).toBeGreaterThan(0)
        expect(screen.getAllByText('Supplier B').length).toBeGreaterThan(0)
      })
    })

    it('renders top suppliers as links', async () => {
      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        const supplierLinks = screen.getAllByRole('link', { name: 'Supplier A' })
        expect(supplierLinks.length).toBeGreaterThan(0)
        expect(supplierLinks[0]).toHaveAttribute('href', '/firma/87654321')
      })
    })

    it('has back link to procurers list', async () => {
      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        const backLink = screen.getByRole('link', { name: /Spat/ })
        expect(backLink).toHaveAttribute('href', '/firmy')
      })
    })

    it('shows loading skeletons while data is loading', async () => {
      global.fetch = vi.fn(async (): Promise<Response> => new Promise(() => {})) as typeof fetch

      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        const skeletons = screen.getAllByTestId('skeleton')
        expect(skeletons.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Detail pages - error handling', () => {
    it('shows error when supplier detail endpoint fails', async () => {
      global.fetch = vi.fn(async (): Promise<Response> => ({
        ok: false,
        status: 500,
        json: async () => ({ message: 'Server error' }),
      } as Response)) as typeof fetch

      renderWithProviders(<SupplierDetailPage />, { route: '/suppliers/87654321', routePattern: '/suppliers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(sk.common.error)).toBeInTheDocument()
      })
    })

    it('shows error when procurer detail endpoint fails', async () => {
      global.fetch = vi.fn(async (): Promise<Response> => ({
        ok: false,
        status: 500,
        json: async () => ({ message: 'Server error' }),
      } as Response)) as typeof fetch

      renderWithProviders(<ProcurerDetailPage />, { route: '/procurers/12345678', routePattern: '/procurers/:ico' })

      await waitFor(() => {
        expect(screen.getByText(sk.common.error)).toBeInTheDocument()
      })
    })
  })
})

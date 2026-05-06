import { describe, it, expect } from 'vitest'
import { renderWithProviders, screen } from './utils'
import { EntityLink } from '../components/entity/EntityLink'
import { SearchPage } from '../pages/SearchPage'
import { SuppliersPage } from '../pages/SuppliersPage'
import { ProcurersPage } from '../pages/ProcurersPage'
import { vi } from 'vitest'

global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  if (url.includes('/contracts')) {
    return {
      ok: true,
      json: async () => ({
        data: [
          {
            id: '1',
            title: 'Contract 1',
            procurer_ico: '12345678',
            procurer_name: 'Procurer A',
            supplier_ico: '87654321',
            supplier_name: 'Supplier A',
            value: 1000,
            year: 2024,
            status: 'completed',
            cpv_code: null,
          },
        ],
        pagination: { total: 1, limit: 20, offset: 0 },
      }),
    } as Response
  }
  if (url.includes('/suppliers')) {
    return {
      ok: true,
      json: async () => ({
        data: [
          { ico: '87654321', name: 'Supplier A', contract_count: 5, total_value: 5000 },
        ],
        pagination: { total: 1, limit: 20, offset: 0 },
      }),
    } as Response
  }
  if (url.includes('/procurers')) {
    return {
      ok: true,
      json: async () => ({
        data: [
          { ico: '12345678', name: 'Procurer A', contract_count: 10, total_spend: 10000 },
        ],
        pagination: { total: 1, limit: 20, offset: 0 },
      }),
    } as Response
  }
  return { ok: false, json: async () => ({}) } as Response
}) as typeof fetch

describe('Entity Linking', () => {
  it('renders supplier link with correct href', () => {
    renderWithProviders(
      <EntityLink ico="87654321" name="Supplier A" type="supplier" />
    )
    const link = screen.getByRole('link', { name: 'Supplier A' })
    expect(link).toHaveAttribute('href', '/firma/87654321')
  })

  it('renders procurer link with correct href', () => {
    renderWithProviders(
      <EntityLink ico="12345678" name="Procurer A" type="procurer" />
    )
    const link = screen.getByRole('link', { name: 'Procurer A' })
    expect(link).toHaveAttribute('href', '/firma/12345678')
  })

  it('uses ico as fallback when name is empty', () => {
    renderWithProviders(
      <EntityLink ico="87654321" name="" type="supplier" />
    )
    const link = screen.getByRole('link', { name: '87654321' })
    expect(link).toBeInTheDocument()
  })

  it('renders dash when no ico and no name', () => {
    renderWithProviders(
      <EntityLink ico="" name="" type="supplier" />
    )
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('does not create link when no ico', () => {
    renderWithProviders(
      <EntityLink ico="" name="Some Name" type="supplier" />
    )
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('Some Name')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    renderWithProviders(
      <EntityLink
        ico="87654321"
        name="Supplier A"
        type="supplier"
        className="custom-class"
      />
    )
    const link = screen.getByRole('link', { name: 'Supplier A' })
    expect(link).toHaveClass('custom-class')
  })

  it('search results render supplier names as links', async () => {
    renderWithProviders(<SearchPage />, { route: '/search' })

    const supplierLink = await screen.findByRole('link', { name: 'Supplier A' })
    expect(supplierLink).toHaveAttribute('href', '/firma/87654321')
  })

  it('search results render procurer names as links', async () => {
    renderWithProviders(<SearchPage />, { route: '/search' })

    const procurerLink = await screen.findByRole('link', { name: 'Procurer A' })
    expect(procurerLink).toHaveAttribute('href', '/firma/12345678')
  })

  it('suppliers list renders each supplier as a link', async () => {
    renderWithProviders(<SuppliersPage />, { route: '/suppliers' })

    const link = await screen.findByRole('link', { name: 'Supplier A' })
    expect(link).toHaveAttribute('href', '/firma/87654321')
  })

  it('procurers list renders each procurer as a link', async () => {
    renderWithProviders(<ProcurersPage />, { route: '/procurers' })

    const link = await screen.findByRole('link', { name: 'Procurer A' })
    expect(link).toHaveAttribute('href', '/firma/12345678')
  })
})

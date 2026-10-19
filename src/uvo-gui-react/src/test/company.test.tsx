import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { createQueryClient } from '@/api/queryClient'
import { FirmaPage } from '@/pages/FirmaPage'
import { FirmaPrehladTab } from '@/pages/firma/FirmaPrehladTab'
import { FirmaPartneriTab } from '@/pages/firma/FirmaPartneriTab'
import { FirmaCpvTab } from '@/pages/firma/FirmaCpvTab'
import { FirmaZakazkyTab } from '@/pages/firma/FirmaZakazkyTab'
import sk from '@/i18n/sk'
import { setupFetch } from './utils'

const PROFILE = {
  ico: '12345678',
  name: 'Acme s.r.o.',
  roles: ['supplier'],
  primary_role: 'supplier',
  stats: {
    as_supplier: { contract_count: 4, total_value: 1000, last_contract_at: '2025-05-01' },
    as_procurer: null,
  },
  top_cpvs: [],
  top_contracts: [
    {
      id: 'c1',
      title: 'Stavba mosta',
      value: 500,
      year: 2025,
      counterparty_name: 'Mesto Žilina',
      counterparty_ico: '00321796',
      role: 'supplier',
    },
  ],
  spend_by_year: [],
}

const PARTNERI = {
  total: 1,
  items: [
    {
      ico: '00321796',
      name: 'Mesto Žilina',
      role: 'procurer',
      contract_count: 3,
      total_value: 900,
      last_contract_at: '2025-04-02',
    },
  ],
}

const CPV = {
  for_company: [
    { code: '45000000-7', label: 'Stavebné práce', total_value: 10, contract_count: 2, percentage: 60 },
  ],
  market_baseline: [],
}

const CONTRACTS = { data: [], pagination: { total: 0, limit: 20, offset: 0 } }

// More specific paths first: setupFetch matches the first key contained in the URL.
const ROUTES = {
  '/partneri': { body: PARTNERI },
  '/cpv-profile': { body: CPV },
  '/contracts': { body: CONTRACTS },
  '/api/firma/12345678': { body: PROFILE },
}

function renderFirma(path: string) {
  const router = createMemoryRouter(
    [
      {
        path: '/firma/:ico',
        element: <FirmaPage />,
        children: [
          { path: 'prehlad', element: <FirmaPrehladTab /> },
          { path: 'zakazky', element: <FirmaZakazkyTab /> },
          { path: 'partneri', element: <FirmaPartneriTab /> },
          { path: 'cpv', element: <FirmaCpvTab /> },
        ],
      },
    ],
    { initialEntries: [path] },
  )
  return render(
    <QueryClientProvider client={createQueryClient({ retry: false, staleTime: Infinity })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('Firma workspace routes', () => {
  let restore: () => void
  afterEach(() => restore?.())

  it('renders the header, labelled section nav and the Prehľad tab', async () => {
    restore = setupFetch(ROUTES)
    renderFirma('/firma/12345678/prehlad')
    expect(await screen.findByRole('heading', { name: 'Acme s.r.o.' })).toBeTruthy()
    expect(screen.getByRole('navigation', { name: sk.firma.sectionsLabel })).toBeTruthy()
    expect(await screen.findByText(sk.firma.colCounterparty)).toBeTruthy()
    expect(screen.getAllByText('Mesto Žilina').length).toBeGreaterThan(0)
  })

  it('renders partner rows on the Partneri tab', async () => {
    restore = setupFetch(ROUTES)
    renderFirma('/firma/12345678/partneri')
    expect(await screen.findByText('Mesto Žilina')).toBeTruthy()
    expect(screen.getByText(sk.firma.roleProcurer)).toBeTruthy()
  })

  it('renders CPV rows on the CPV tab', async () => {
    restore = setupFetch(ROUTES)
    renderFirma('/firma/12345678/cpv')
    expect(await screen.findByText('Stavebné práce')).toBeTruthy()
    expect(screen.getByText(sk.firma.colShare)).toBeTruthy()
  })

  it('shows the empty state on the Zákazky tab when there are no contracts', async () => {
    restore = setupFetch(ROUTES)
    renderFirma('/firma/12345678/zakazky')
    expect(await screen.findByText(sk.firma.zakazkyEmpty)).toBeTruthy()
  })

  it('shows not-found for a 404 profile', async () => {
    restore = setupFetch({ '/api/firma/': { status: 404, body: { detail: 'nope' } } })
    renderFirma('/firma/99999999/prehlad')
    await waitFor(() => expect(screen.getByText(sk.firma.notFound)).toBeTruthy())
    expect(screen.getByText(sk.firma.notFoundDetail.replace('{ico}', '99999999'))).toBeTruthy()
  })
})

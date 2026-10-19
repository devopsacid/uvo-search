import { describe, it, expect, afterEach } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import { renderWithProviders, screen, fireEvent, setupFetch } from './utils'
import { GlobalSearch } from '@/components/search/GlobalSearch'
import sk from '@/i18n/sk'

const UNIFIED = {
  q: 'sta',
  companies: [{ ico: '12345678', name: 'Stavebná firma s.r.o.', roles: ['supplier'], contract_count: 3 }],
  contracts: [{ id: 'abc123', title: 'Rekonštrukcia mosta', procurer_name: 'Mesto', value: 1000, year: 2024 }],
}

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname + loc.search}</div>
}

function renderSearch() {
  return renderWithProviders(
    <Routes>
      <Route path="*" element={<><GlobalSearch /><Where /></>} />
    </Routes>,
  )
}

let restore: () => void
afterEach(() => restore?.())

describe('GlobalSearch (unified search contract)', () => {
  it('reads `companies` and `contracts` keys and renders both groups', async () => {
    restore = setupFetch({ '/api/search/unified': { body: UNIFIED } })
    renderSearch()
    fireEvent.change(screen.getByLabelText(sk.globalSearch.placeholder), { target: { value: 'sta' } })
    expect(await screen.findByText('Stavebná firma s.r.o.')).toBeInTheDocument()
    expect(screen.getByText('Rekonštrukcia mosta')).toBeInTheDocument()
    expect(screen.getByText(sk.globalSearch.sectionCompanies)).toBeInTheDocument()
    expect(screen.getByText(sk.globalSearch.sectionContracts)).toBeInTheDocument()
  })

  it('navigates to the new company and contract routes', async () => {
    restore = setupFetch({ '/api/search/unified': { body: UNIFIED } })
    renderSearch()
    const input = screen.getByLabelText(sk.globalSearch.placeholder)
    fireEvent.change(input, { target: { value: 'sta' } })
    fireEvent.mouseDown((await screen.findByText('Stavebná firma s.r.o.')).closest('[role="option"]')!)
    expect(screen.getByTestId('where')).toHaveTextContent('/company/12345678')

    fireEvent.change(input, { target: { value: 'sta' } })
    fireEvent.mouseDown((await screen.findByText('Rekonštrukcia mosta')).closest('[role="option"]')!)
    expect(screen.getByTestId('where')).toHaveTextContent('/contracts?selected=abc123')
  })

  it('Enter on free text opens the unified search page at /search', async () => {
    restore = setupFetch({ '/api/search/unified': { body: { q: 'x', companies: [], contracts: [] } } })
    renderSearch()
    const input = screen.getByLabelText(sk.globalSearch.placeholder)
    fireEvent.change(input, { target: { value: 'most' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByTestId('where')).toHaveTextContent('/search?q=most')
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, fireEvent, waitFor } from './utils'
import { ContractsPage } from '../pages/ContractsPage'
import { makeAnalyticsFetch } from './fixtures/analytics'
import sk from '../i18n/sk'

function lastContractsUrl(calls: string[]): URL {
  const url = [...calls].reverse().find((c) => c.includes('/contracts?'))
  if (!url) throw new Error('no /contracts request was made')
  return new URL(url, 'http://localhost')
}

describe('ContractsPage as drill-down target', () => {
  let calls: string[]

  beforeEach(() => {
    const f = makeAnalyticsFetch()
    calls = f.calls
    global.fetch = vi.fn(f.impl) as typeof fetch
  })

  it('sends procurer_ico, supplier_ico, source, cpv and the date range to the API', async () => {
    renderWithProviders(<ContractsPage />, {
      route: '/contracts?date_from=2023-01-01&date_to=2023-12-31&cpv=45&source=crz&procurer_ico=111&supplier_ico=222',
    })
    await waitFor(() => expect(calls.some((c) => c.includes('/contracts?'))).toBe(true))
    const p = lastContractsUrl(calls).searchParams
    expect(p.get('date_from')).toBe('2023-01-01')
    expect(p.get('date_to')).toBe('2023-12-31')
    expect(p.get('cpv')).toBe('45')
    expect(p.get('source')).toBe('crz')
    expect(p.get('procurer_ico')).toBe('111')
    expect(p.get('supplier_ico')).toBe('222')
    expect(p.has('ico')).toBe(false)
  })

  it('lets date_from/date_to take precedence over year', async () => {
    renderWithProviders(<ContractsPage />, {
      route: '/contracts?year=2020&date_from=2023-02-01&date_to=2023-03-31',
    })
    await waitFor(() => expect(calls.some((c) => c.includes('/contracts?'))).toBe(true))
    const p = lastContractsUrl(calls).searchParams
    expect(p.get('date_from')).toBe('2023-02-01')
    expect(p.get('date_to')).toBe('2023-03-31')
  })

  it('still derives the range from year when no explicit dates are given', async () => {
    renderWithProviders(<ContractsPage />, { route: '/contracts?year=2021' })
    await waitFor(() => expect(calls.some((c) => c.includes('/contracts?'))).toBe(true))
    const p = lastContractsUrl(calls).searchParams
    expect(p.get('date_from')).toBe('2021-01-01')
    expect(p.get('date_to')).toBe('2021-12-31')
  })

  it('shows removable chips for the active drill-down filters', async () => {
    renderWithProviders(<ContractsPage />, {
      route: '/contracts?date_from=2023-01-01&date_to=2023-12-31&source=crz&procurer_ico=111',
    })
    const chips = await screen.findByRole('list', { name: sk.analytics.activeFilters })
    expect(chips).toHaveTextContent(sk.analytics.filters.sources.crz)
    expect(chips).toHaveTextContent('111')

    fireEvent.click(screen.getByRole('button', { name: /Odstrániť filter: Zdroj/ }))
    await waitFor(() => expect(screen.queryByRole('list', { name: sk.analytics.activeFilters })).toHaveTextContent('111'))
    expect(screen.getByRole('list', { name: sk.analytics.activeFilters })).not.toHaveTextContent(
      sk.analytics.filters.sources.crz,
    )
  })

  it('offers a source select', async () => {
    renderWithProviders(<ContractsPage />, { route: '/contracts?source=itms' })
    const select = await screen.findByLabelText(sk.analytics.filters.source)
    expect(select).toHaveValue('itms')
  })
})

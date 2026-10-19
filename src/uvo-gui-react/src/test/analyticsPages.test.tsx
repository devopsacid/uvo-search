import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useLocation } from 'react-router-dom'
import { renderWithProviders, screen, fireEvent, waitFor, within } from './utils'
import { PrehladPage } from '@/pages/analytics/PrehladPage'
import { KoncentraciaPage } from '@/pages/analytics/KoncentraciaPage'
import { CpvPage } from '@/pages/analytics/CpvPage'
import { PokrytiePage } from '@/pages/analytics/PokrytiePage'
import { FirmaPrehladTab } from '@/pages/firma/FirmaPrehladTab'
import { downloadCsv } from '@/lib/csv'
import { formatCurrency as rawCurrency, formatNumber as rawNumber } from '@/lib/utils'
import { defaultRange } from '@/lib/analyticsFilters'
import {
  concentrationFixture,
  coverageFixture,
  makeAnalyticsFetch,
  summaryFixture,
  timeseriesFixture,
  topSuppliersFixture,
} from './fixtures/analytics'
import sk from '@/i18n/sk'

vi.mock('@/lib/csv', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/csv')>()),
  downloadCsv: vi.fn(),
}))

function Probe() {
  const { pathname, search } = useLocation()
  return <output data-testid="loc">{pathname + search}</output>
}

type Overrides = Parameters<typeof makeAnalyticsFetch>[0]

function install(overrides: Overrides = {}) {
  const f = makeAnalyticsFetch(overrides)
  global.fetch = vi.fn(f.impl) as typeof fetch
  return f
}

// Testing Library collapses whitespace (incl. NBSP) in element text, so normalise expectations too.
const norm = (s: string) => s.replace(/\s+/g, ' ')
const formatCurrency = (v: number) => norm(rawCurrency(v))
const formatNumber = (v: number) => norm(rawNumber(v))

const hrefOf = (el: HTMLElement) => new URL(el.getAttribute('href') ?? '', 'http://localhost')
const figureOf = (title: string) => screen.getByRole('heading', { name: title }).closest('figure') as HTMLElement

beforeEach(() => {
  vi.mocked(downloadCsv).mockClear()
})

describe('PrehladPage', () => {
  it('shows skeletons first, then KPIs, charts and tables', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0)

    expect(await screen.findByText(formatCurrency(summaryFixture.current.total_value))).toBeInTheDocument()
    expect(screen.getByText(formatNumber(summaryFixture.current.contract_count))).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.kpi.supplierCount)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryAllByTestId('skeleton')).toHaveLength(0))
    expect(screen.getByRole('img', { name: /najvyššia hodnota 2023/ })).toBeInTheDocument()
  })

  it('shows signed deltas against the previous period and a dash when there is none', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    const valueTile = (await screen.findByText(sk.analytics.kpi.totalValue)).closest('a') as HTMLElement
    expect(valueTile).toHaveTextContent('+10,5')
    expect(valueTile).toHaveTextContent(sk.analytics.kpi.deltaVsPrevious)
    const avgTile = screen.getByText(sk.analytics.kpi.avgValue).closest('a') as HTMLElement
    expect(avgTile).toHaveTextContent('-7,9')
    const supplierTile = screen.getByText(sk.analytics.kpi.supplierCount).closest('a') as HTMLElement
    expect(supplierTile).toHaveTextContent(sk.analytics.kpi.noComparison)
  })

  it('KPI tiles drill down to the contract list with the effective filters', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad?cpv=45&source=crz' })
    const tile = (await screen.findByText(sk.analytics.kpi.contractCount)).closest('a') as HTMLElement
    const url = hrefOf(tile)
    expect(url.pathname).toBe('/zakazky')
    expect(url.searchParams.get('cpv')).toBe('45')
    expect(url.searchParams.get('source')).toBe('crz')
    expect(url.searchParams.get('date_from')).toBe(defaultRange().date_from)
  })

  it('sends the filters to the API, defaults applied in memory', async () => {
    const f = install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad?cpv=45' })
    await screen.findByText(sk.analytics.kpi.contractCount)
    const summary = f.calls.find((c) => c.includes('/analytics/summary')) as string
    const p = new URL(summary, 'http://localhost').searchParams
    expect(p.get('cpv')).toBe('45')
    expect(p.get('date_from')).toBe(defaultRange().date_from)
    expect(p.get('date_to')).toBe(defaultRange().date_to)
  })

  it('top lists: the bar drills to /zakazky with the entity, the name opens the firma workspace', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    const bar = await screen.findByRole('link', { name: /Zobraziť zákazky: Skanska SK/ })
    const url = hrefOf(bar)
    expect(url.pathname).toBe('/zakazky')
    expect(url.searchParams.get('supplier_ico')).toBe('36396567')

    expect(hrefOf(screen.getByRole('link', { name: 'Skanska SK' })).pathname).toBe('/firma/36396567')

    const procurerBar = screen.getByRole('link', { name: /Zobraziť zákazky: Slovenská správa ciest/ })
    expect(hrefOf(procurerBar).searchParams.get('procurer_ico')).toBe('00151742')
  })

  it('top lists are keyboard reachable links and "Ostatní" is not a link', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    const bar = await screen.findByRole('link', { name: /Zobraziť zákazky: Skanska SK/ })
    // A native anchor with an href is in the tab order and activates with Enter.
    expect(bar.tagName).toBe('A')
    expect(bar).toHaveAttribute('href')
    expect(bar).not.toHaveAttribute('tabindex', '-1')
    expect(screen.getAllByText(sk.analytics.otherEntities).length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: new RegExp(`Zobraziť zákazky: ${sk.analytics.otherEntities}`) })).toBeNull()
  })

  it('switching the metric re-queries the ranking by contract count', async () => {
    const f = install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    const card = within((await screen.findByRole('heading', { name: sk.analytics.prehlad.topSuppliers })).closest('figure') as HTMLElement)
    fireEvent.click(card.getByRole('button', { name: sk.analytics.prehlad.metricCount }))
    await waitFor(() =>
      expect(f.calls.some((c) => c.includes('dimension=supplier') && c.includes('metric=contract_count'))).toBe(true),
    )
  })

  it('time series table view links each period to the contract list for that bucket', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    await screen.findByText(formatCurrency(summaryFixture.current.total_value))
    await waitFor(() => expect(screen.getByRole('img', { name: /najvyššia hodnota/ })).toBeInTheDocument())
    const card = within(figureOf(sk.analytics.prehlad.timeseriesTitle))
    fireEvent.click(card.getByRole('button', { name: sk.analytics.charts.showTable }))
    const link = card.getByRole('link', { name: '2023' })
    const url = hrefOf(link)
    expect(url.pathname).toBe('/zakazky')
    expect(url.searchParams.get('date_from')).toBe('2023-01-01')
    expect(url.searchParams.get('date_to')).toBe('2023-12-31')
  })

  it('changing the granularity re-queries the time series', async () => {
    const f = install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    await screen.findByText(formatCurrency(summaryFixture.current.total_value))
    fireEvent.change(screen.getByLabelText(sk.analytics.prehlad.granularity), { target: { value: 'quarter' } })
    await waitFor(() => expect(f.calls.some((c) => c.includes('/analytics/timeseries') && c.includes('granularity=quarter'))).toBe(true))
  })

  it('uses months automatically for spans up to 3 years', async () => {
    const f = install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad?date_from=2024-01-01&date_to=2025-06-30' })
    await screen.findByText(sk.analytics.kpi.contractCount)
    await waitFor(() => expect(f.calls.some((c) => c.includes('/analytics/timeseries') && c.includes('granularity=month'))).toBe(true))
  })

  it('recent contracts link to the list with the contract selected', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    const link = await screen.findByRole('link', { name: /Rekonštrukcia cesty I\/18/ })
    const url = hrefOf(link)
    expect(url.pathname).toBe('/zakazky')
    expect(url.searchParams.get('selected')).toBe('c-1')
    expect(url.searchParams.get('date_from')).toBe(defaultRange().date_from)
  })

  it('shows empty states when nothing matches', async () => {
    install({
      '/analytics/timeseries': { body: { ...timeseriesFixture, points: [] } },
      '/analytics/top': { body: { ...topSuppliersFixture, items: [], other: { total_value: 0, contract_count: 0, share_pct: 0 } } },
    })
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    expect((await screen.findAllByText(sk.analytics.charts.emptyTitle)).length).toBeGreaterThanOrEqual(3)
  })

  it('shows an error with retry that recovers', async () => {
    const overrides: Overrides = { '/analytics/timeseries': { status: 500, body: { detail: 'boom' } } }
    install(overrides)
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('boom')

    overrides['/analytics/timeseries'] = { body: timeseriesFixture }
    fireEvent.click(within(alert).getByRole('button', { name: sk.analytics.charts.retry }))
    expect(await screen.findByRole('img', { name: /najvyššia hodnota/ })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('does not call the API for an invalid range', async () => {
    const f = install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad?date_from=2024-05-01&date_to=2024-01-01' })
    await new Promise((r) => setTimeout(r, 30))
    expect(f.calls.filter((c) => c.includes('/analytics/'))).toHaveLength(0)
  })

  it('exports the time series as CSV', async () => {
    install()
    renderWithProviders(<PrehladPage />, { route: '/analytika/prehlad' })
    await screen.findByText(formatCurrency(summaryFixture.current.total_value))
    await screen.findByRole('img', { name: /najvyššia hodnota/ })
    const card = within(figureOf(sk.analytics.prehlad.timeseriesTitle))
    fireEvent.click(card.getByRole('button', { name: sk.analytics.charts.exportCsv }))
    expect(downloadCsv).toHaveBeenCalledTimes(1)
    const [filename, csv] = vi.mocked(downloadCsv).mock.calls[0]
    const def = defaultRange()
    expect(filename).toBe(`uvo-cas-${def.date_from}_${def.date_to}.csv`)
    expect(csv.startsWith('﻿')).toBe(true)
    expect(csv).toContain(`${sk.analytics.csv.period};${sk.analytics.csv.totalValue}`)
    expect(csv).toContain('2023;1200000000;300;4000000')
  })
})

describe('KoncentraciaPage', () => {
  it('shows HHI with its band, CR4, CR10 and entity count', async () => {
    install()
    renderWithProviders(<KoncentraciaPage />, { route: '/analytika/koncentracia' })
    expect(await screen.findByText(formatNumber(1820))).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.koncentracia.bands.moderate)).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.koncentracia.cr4)).toBeInTheDocument()
    expect(screen.getByText(formatNumber(concentrationFixture.entity_count))).toBeInTheDocument()
  })

  it('table rows open the firma workspace and the filtered contract list', async () => {
    install()
    renderWithProviders(<KoncentraciaPage />, { route: '/analytika/koncentracia?cpv=45' })
    const firma = await screen.findByRole('link', { name: 'Skanska SK' })
    expect(hrefOf(firma).pathname).toBe('/firma/36396567')
    const rows = screen.getAllByRole('link', { name: sk.analytics.charts.showContracts })
    const url = hrefOf(rows[0])
    expect(url.pathname).toBe('/zakazky')
    expect(url.searchParams.get('supplier_ico')).toBe('36396567')
    expect(url.searchParams.get('cpv')).toBe('45')
  })

  it('has an "Ostatní" segment and a legend (never colour-only)', async () => {
    install()
    renderWithProviders(<KoncentraciaPage />, { route: '/analytika/koncentracia' })
    await screen.findByRole('link', { name: 'Skanska SK' })
    expect(screen.getByText(sk.analytics.otherEntities)).toBeInTheDocument()
  })

  it('switches the dimension through the URL and re-queries', async () => {
    const f = install()
    renderWithProviders(
      <>
        <KoncentraciaPage />
        <Probe />
      </>,
      { route: '/analytika/koncentracia' },
    )
    await screen.findByRole('link', { name: 'Skanska SK' })
    fireEvent.click(screen.getByRole('button', { name: sk.analytics.koncentracia.dimensions.procurer }))
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toContain('dimension=procurer'))
    await waitFor(() => expect(f.calls.some((c) => c.includes('/analytics/concentration') && c.includes('dimension=procurer'))).toBe(true))
  })

  it('requests one HHI per year in parallel and offers the numbers as a table', async () => {
    const f = install()
    renderWithProviders(<KoncentraciaPage />, { route: '/analytika/koncentracia?date_from=2022-01-01&date_to=2024-12-31' })
    await waitFor(() => {
      const years = new Set(
        f.calls
          .filter((c) => c.includes('/analytics/concentration'))
          .map((c) => new URL(c, 'http://localhost').searchParams)
          .filter((p) => p.get('date_from')?.endsWith('-01-01') && p.get('date_to')?.endsWith('-12-31') && p.get('date_from')?.slice(0, 4) === p.get('date_to')?.slice(0, 4))
          .map((p) => p.get('date_from')?.slice(0, 4)),
      )
      expect([...years].sort()).toEqual(['2022', '2023', '2024'])
    })
    const card = within(figureOf(sk.analytics.koncentracia.trendTitle))
    await waitFor(() => expect(card.getByRole('img')).toBeInTheDocument())
    fireEvent.click(card.getByRole('button', { name: sk.analytics.charts.showTable }))
    expect(card.getByRole('columnheader', { name: sk.analytics.koncentracia.bandColumn })).toBeInTheDocument()
    expect(card.getAllByRole('row')).toHaveLength(4)
  })

  it('shows the empty state when the filtered market has no entities', async () => {
    install({ '/analytics/concentration': { body: { ...concentrationFixture, entity_count: 0, hhi: 0, hhi_band: 'low', top: [] } } })
    renderWithProviders(<KoncentraciaPage />, { route: '/analytika/koncentracia' })
    expect((await screen.findAllByText(sk.analytics.charts.emptyTitle)).length).toBeGreaterThan(0)
  })

  it('shows an error with retry', async () => {
    install({ '/analytics/concentration': { status: 504, body: { detail: 'analytics_timeout' } } })
    renderWithProviders(<KoncentraciaPage />, { route: '/analytika/koncentracia' })
    const alerts = await screen.findAllByRole('alert')
    expect(alerts[0]).toHaveTextContent(sk.analytics.charts.timeout)
    expect(within(alerts[0]).getByRole('button', { name: sk.analytics.charts.retry })).toBeInTheDocument()
  })
})

describe('CpvPage', () => {
  it('lists divisions; a bar narrows the dashboard to that sector', async () => {
    install()
    renderWithProviders(<CpvPage />, { route: '/analytika/cpv' })
    const bar = await screen.findByRole('link', { name: /Zobraziť zákazky: 45 · Stavebné práce/ })
    const url = hrefOf(bar)
    expect(url.pathname).toBe('/analytika/cpv')
    expect(url.searchParams.get('cpv')).toBe('45')
  })

  it('has an "Ostatné" bucket only beyond the top 10 and an All-sectors table with contract links', async () => {
    install()
    renderWithProviders(<CpvPage />, { route: '/analytika/cpv' })
    await screen.findByRole('table', { name: sk.analytics.cpv.tableTitle })
    const table = within(screen.getByRole('table', { name: sk.analytics.cpv.tableTitle }))
    const links = table.getAllByRole('link', { name: sk.analytics.charts.showContracts })
    const url = hrefOf(links[0])
    expect(url.pathname).toBe('/zakazky')
    expect(url.searchParams.get('cpv')).toBe('45')
    expect(screen.queryByText(sk.analytics.otherSectors)).toBeNull()
  })

  it('sorts the table by a column and exposes aria-sort', async () => {
    install()
    renderWithProviders(<CpvPage />, { route: '/analytika/cpv' })
    const table = await screen.findByRole('table', { name: sk.analytics.cpv.tableTitle })
    const firstCode = () => within(table).getAllByRole('row')[1].querySelector('td')?.textContent
    expect(firstCode()).toBe('45')
    const codeHeader = within(table).getByRole('columnheader', { name: new RegExp(sk.analytics.cpv.colCode) })
    fireEvent.click(within(codeHeader).getByRole('button'))
    expect(codeHeader).toHaveAttribute('aria-sort', 'ascending')
    expect(firstCode()).toBe('00')
  })

  it('requests the top 5 divisions over time and drills to groups when a sector is selected', async () => {
    const f = install()
    renderWithProviders(<CpvPage />, { route: '/analytika/cpv?cpv=45' })
    await screen.findByText(sk.analytics.cpv.sharesTitleGroup)
    expect(f.calls.some((c) => c.includes('/analytics/cpv') && c.includes('level=group'))).toBe(true)
    expect(f.calls.some((c) => c.includes('/analytics/timeseries') && c.includes('split_by=cpv_division') && c.includes('top=5'))).toBe(true)
  })

  it('shows the trend as a table with one column per series', async () => {
    install()
    renderWithProviders(<CpvPage />, { route: '/analytika/cpv' })
    await screen.findByRole('table', { name: sk.analytics.cpv.tableTitle })
    const card = within(figureOf(sk.analytics.cpv.trendTitle))
    await waitFor(() => expect(card.getByRole('img')).toBeInTheDocument())
    fireEvent.click(card.getByRole('button', { name: sk.analytics.charts.showTable }))
    expect(card.getByRole('columnheader', { name: 'Stavebné práce' })).toBeInTheDocument()
    expect(card.getByRole('columnheader', { name: sk.analytics.otherSectors })).toBeInTheDocument()
  })

  it('shows empty and error states', async () => {
    install({ '/analytics/cpv': { body: { ...(await import('./fixtures/analytics')).cpvFixture, items: [] } } })
    renderWithProviders(<CpvPage />, { route: '/analytika/cpv' })
    expect((await screen.findAllByText(sk.analytics.charts.emptyTitle)).length).toBeGreaterThan(0)
  })

  it('shows an error panel with retry when the CPV query fails', async () => {
    install({ '/analytics/cpv': { status: 500, body: { detail: 'down' } } })
    renderWithProviders(<CpvPage />, { route: '/analytika/cpv' })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('down')
    expect(within(alert).getByRole('button', { name: sk.analytics.charts.retry })).toBeInTheDocument()
  })
})

describe('PokrytiePage', () => {
  it('shows a card per source with status and age', async () => {
    const f = install()
    renderWithProviders(<PokrytiePage />, { route: '/analytika/pokrytie?cpv=45&date_from=2020-01-01' })
    expect(await screen.findByRole('heading', { name: sk.analytics.filters.sources.vestnik })).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.pokrytie.status.healthy)).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.pokrytie.status.legacy)).toBeInTheDocument()
    expect(screen.getByText('pred 2 h')).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.pokrytie.never)).toBeInTheDocument()
    // coverage ignores the filters entirely
    const call = f.calls.find((c) => c.includes('/analytics/coverage')) as string
    expect(call).not.toContain('?')
  })

  it('shows the data-quality table, the monthly table view and the canonical KPIs', async () => {
    install()
    renderWithProviders(<PokrytiePage />, { route: '/analytika/pokrytie' })
    const quality = await screen.findByRole('table', { name: sk.analytics.pokrytie.qualityTitle })
    expect(within(quality).getByText(/82,5/)).toBeInTheDocument()
    expect(screen.getByText(formatNumber(coverageFixture.canonical.notices_with_canonical_id))).toBeInTheDocument()

    const card = within(figureOf(sk.analytics.pokrytie.monthlyTitle))
    await waitFor(() => expect(card.getByRole('img')).toBeInTheDocument())
    fireEvent.click(card.getByRole('button', { name: sk.analytics.charts.showTable }))
    expect(card.getByRole('cell', { name: '09/2026' })).toBeInTheDocument()
  })

  it('shows an error state with retry', async () => {
    install({ '/analytics/coverage': { status: 500, body: { detail: 'nope' } } })
    renderWithProviders(<PokrytiePage />, { route: '/analytika/pokrytie' })
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0)
  })
})

describe('Firma workspace integration', () => {
  const PROCURER = {
    ico: '00151742',
    name: 'Slovenská správa ciest',
    roles: ['procurer'],
    primary_role: 'procurer',
    stats: { as_supplier: null, as_procurer: { contract_count: 30, total_value: 800, last_contract_at: '2025-05-01' } },
    top_cpvs: [],
    top_contracts: [],
    spend_by_year: [],
  }

  it('shows supplier concentration for procurers and links into the analytics', async () => {
    const f = install({ '/api/firma/00151742': { body: PROCURER } })
    renderWithProviders(<FirmaPrehladTab />, { route: '/firma/00151742/prehlad', routePattern: '/firma/:ico/prehlad' })
    expect(await screen.findByText(sk.firma.supplierConcentration)).toBeInTheDocument()
    expect(await screen.findByText(formatNumber(1820))).toBeInTheDocument()
    const call = f.calls.find((c) => c.includes('/analytics/concentration')) as string
    const p = new URL(call, 'http://localhost').searchParams
    expect(p.get('procurer_ico')).toBe('00151742')
    expect(p.get('dimension')).toBe('supplier')

    const link = screen.getByRole('link', { name: sk.firma.analyticsLink })
    const url = hrefOf(link)
    expect(url.pathname).toBe('/analytika/prehlad')
    expect(url.searchParams.get('procurer_ico')).toBe('00151742')
  })

  it('does not query concentration for a pure supplier', async () => {
    const f = install({
      '/api/firma/12345678': {
        body: { ...PROCURER, ico: '12345678', stats: { as_supplier: { contract_count: 4, total_value: 10, last_contract_at: null }, as_procurer: null } },
      },
    })
    renderWithProviders(<FirmaPrehladTab />, { route: '/firma/12345678/prehlad', routePattern: '/firma/:ico/prehlad' })
    const link = await screen.findByRole('link', { name: sk.firma.analyticsLink })
    expect(hrefOf(link).searchParams.get('supplier_ico')).toBe('12345678')
    expect(f.calls.some((c) => c.includes('/analytics/concentration'))).toBe(false)
  })
})

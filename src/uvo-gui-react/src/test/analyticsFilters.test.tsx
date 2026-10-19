import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useLocation } from 'react-router-dom'
import { renderWithProviders, screen, fireEvent, waitFor } from './utils'
import { AnalyticsFilterBar } from '@/components/analytics/AnalyticsFilterBar'
import { defaultRange, presetRange } from '@/lib/analyticsFilters'
import { makeAnalyticsFetch } from './fixtures/analytics'
import sk from '@/i18n/sk'

function Probe() {
  const { search } = useLocation()
  return <output data-testid="search">{search}</output>
}

function renderBar(route = '/analytika/prehlad') {
  return renderWithProviders(
    <>
      <AnalyticsFilterBar />
      <Probe />
    </>,
    { route },
  )
}

const search = () => new URLSearchParams(screen.getByTestId('search').textContent ?? '')

describe('AnalyticsFilterBar', () => {
  let calls: string[]

  beforeEach(() => {
    const f = makeAnalyticsFetch()
    calls = f.calls
    global.fetch = vi.fn(f.impl) as typeof fetch
  })
  afterEach(() => vi.restoreAllMocks())

  it('shows the default range without writing it to the URL', () => {
    renderBar()
    const def = defaultRange()
    expect(screen.getByLabelText(sk.analytics.filters.dateFrom)).toHaveValue(def.date_from)
    expect(screen.getByLabelText(sk.analytics.filters.dateTo)).toHaveValue(def.date_to)
    expect(screen.getByTestId('search').textContent).toBe('')
    expect(screen.getByRole('button', { name: sk.analytics.filters.presets.last5 })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.queryByRole('button', { name: sk.analytics.filters.reset })).toBeNull()
  })

  it('round-trips URL state into the controls', () => {
    renderBar('/analytika/prehlad?date_from=2023-01-01&date_to=2023-12-31&cpv=45&source=crz')
    expect(screen.getByLabelText(sk.analytics.filters.dateFrom)).toHaveValue('2023-01-01')
    expect(screen.getByLabelText(sk.analytics.filters.dateTo)).toHaveValue('2023-12-31')
    expect(screen.getByLabelText(sk.analytics.filters.cpv)).toHaveValue('45')
    expect(screen.getByLabelText(sk.analytics.filters.source)).toHaveValue('crz')
    expect(screen.getByRole('button', { name: sk.analytics.filters.reset })).toBeInTheDocument()
  })

  it('writes a preset to the URL and removes it again when the default preset is chosen', async () => {
    renderBar()
    fireEvent.click(screen.getByRole('button', { name: sk.analytics.filters.presets.lastYear }))
    const last = presetRange('lastYear')
    await waitFor(() => expect(search().get('date_from')).toBe(last.date_from))
    expect(search().get('date_to')).toBe(last.date_to)

    fireEvent.click(screen.getByRole('button', { name: sk.analytics.filters.presets.last5 }))
    await waitFor(() => expect(search().has('date_from')).toBe(false))
    expect(search().has('date_to')).toBe(false)
  })

  it('"Všetko" keeps only the non-default start date in the URL', async () => {
    renderBar()
    fireEvent.click(screen.getByRole('button', { name: sk.analytics.filters.presets.all }))
    await waitFor(() => expect(search().get('date_from')).toBe('2014-01-01'))
    expect(search().has('date_to')).toBe(false)
  })

  it('commits the source select and resets all filters', async () => {
    renderBar('/analytika/prehlad?cpv=45')
    fireEvent.change(screen.getByLabelText(sk.analytics.filters.source), { target: { value: 'ted' } })
    await waitFor(() => expect(search().get('source')).toBe('ted'))
    expect(search().get('cpv')).toBe('45')

    fireEvent.click(screen.getByRole('button', { name: sk.analytics.filters.reset }))
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''))
  })

  it('commits the CPV prefix on blur and ignores non-digits', async () => {
    renderBar()
    const input = screen.getByLabelText(sk.analytics.filters.cpv)
    fireEvent.change(input, { target: { value: '4a5' } })
    expect(input).toHaveValue('45')
    fireEvent.blur(input)
    await waitFor(() => expect(search().get('cpv')).toBe('45'))
  })

  it('does not commit a one-digit CPV prefix (the API needs 2 to 8 digits)', () => {
    renderBar()
    const input = screen.getByLabelText(sk.analytics.filters.cpv)
    fireEvent.change(input, { target: { value: '4' } })
    fireEvent.blur(input)
    expect(search().has('cpv')).toBe(false)
  })

  it('flags a reversed range with an alert', () => {
    renderBar('/analytika/prehlad?date_from=2024-05-01&date_to=2024-01-01')
    expect(screen.getByRole('alert')).toHaveTextContent(sk.analytics.filters.rangeReversed)
  })

  it('flags a range longer than 15 years', () => {
    renderBar('/analytika/prehlad?date_from=2005-01-01&date_to=2024-01-01')
    expect(screen.getByRole('alert')).toHaveTextContent(sk.analytics.filters.rangeSpan)
  })

  it('copies the current view URL and announces it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderBar('/analytika/prehlad?date_from=2023-01-01&date_to=2023-12-31&cpv=45')
    fireEvent.click(screen.getByRole('button', { name: sk.analytics.filters.copyLink }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    const copied = new URL(writeText.mock.calls[0][0] as string)
    expect(copied.pathname).toBe('/analytika/prehlad')
    expect(copied.searchParams.get('cpv')).toBe('45')
    expect(copied.searchParams.get('date_from')).toBe('2023-01-01')
    expect((await screen.findAllByText(sk.analytics.filters.linkCopied)).length).toBeGreaterThan(0)
  })

  it('offers CPV divisions from the API as datalist options', async () => {
    const { container } = renderBar()
    await waitFor(() => expect(container.querySelectorAll('datalist option').length).toBeGreaterThan(0))
    expect(container.querySelector('datalist option[value="45"]')).toHaveTextContent('Stavebné práce')
    expect(calls.some((c) => c.includes('/analytics/cpv'))).toBe(true)
  })
})

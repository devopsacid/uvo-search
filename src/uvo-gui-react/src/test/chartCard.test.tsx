import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders, screen, fireEvent } from './utils'
import { ChartCard, type ChartQueryState } from '@/components/analytics/ChartCard'
import { SimpleDataTable } from '@/components/analytics/DataTableToggle'
import sk from '@/i18n/sk'

const ok: ChartQueryState = { isLoading: false, isError: false, error: null, isFetching: false, refetch: vi.fn() }

function renderCard(
  props: Partial<React.ComponentProps<typeof ChartCard>> = {},
  route = '/analytics/overview',
) {
  return renderWithProviders(
    <ChartCard
      title="Objem v čase"
      caption="Obdobie: 2022 – 2026"
      ariaLabel="Objem podľa rokov, najvyšší 2023"
      status={ok}
      isEmpty={false}
      chart={<svg data-testid="chart" />}
      table={
        <SimpleDataTable
          caption="Objem v čase"
          rows={[{ y: '2023', v: 5 }]}
          rowKey={(r) => r.y}
          columns={[
            { header: 'Rok', cell: (r) => r.y },
            { header: 'Hodnota', cell: (r) => r.v },
          ]}
        />
      }
      onExportCsv={vi.fn()}
      {...props}
    />,
    { route },
  )
}

describe('ChartCard states', () => {
  it('renders a figure with caption and an image role with the summary label', () => {
    renderCard()
    expect(screen.getByRole('heading', { name: 'Objem v čase' })).toBeInTheDocument()
    expect(screen.getByText('Obdobie: 2022 – 2026')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Objem podľa rokov, najvyšší 2023' })).toContainElement(
      screen.getByTestId('chart'),
    )
  })

  it('shows a skeleton while loading and disables export', () => {
    renderCard({ status: { ...ok, isLoading: true } })
    expect(screen.getByRole('status', { name: sk.analytics.charts.loading })).toBeInTheDocument()
    expect(screen.getByTestId('skeleton')).toBeInTheDocument()
    expect(screen.queryByTestId('chart')).toBeNull()
    expect(screen.getByRole('button', { name: sk.analytics.charts.exportCsv })).toBeDisabled()
  })

  it('shows the error with a retry that refetches', () => {
    const refetch = vi.fn()
    renderCard({ status: { ...ok, isError: true, error: new Error('HTTP 500'), refetch } })
    expect(screen.getByRole('alert')).toHaveTextContent(sk.analytics.charts.errorTitle)
    expect(screen.getByRole('alert')).toHaveTextContent('HTTP 500')
    fireEvent.click(screen.getByRole('button', { name: sk.analytics.charts.retry }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('explains a server-side timeout in plain language', () => {
    renderCard({ status: { ...ok, isError: true, error: new Error('analytics_timeout') } })
    expect(screen.getByRole('alert')).toHaveTextContent(sk.analytics.charts.timeout)
  })

  it('shows the empty state; with an off-default period it offers to widen it', () => {
    renderCard({ isEmpty: true }, '/analytics/overview?date_from=2024-01-01&date_to=2024-02-01')
    expect(screen.getByText(sk.analytics.charts.emptyTitle)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: sk.analytics.charts.widenPeriod })).toBeInTheDocument()
  })

  it('with entity filters active the empty state offers to clear them', () => {
    renderCard({ isEmpty: true }, '/analytics/overview?cpv=45')
    expect(screen.getByRole('button', { name: sk.common.clearFilters })).toBeInTheDocument()
  })

  it('has no empty-state action on the default view', () => {
    renderCard({ isEmpty: true })
    expect(screen.queryByRole('button', { name: sk.analytics.charts.widenPeriod })).toBeNull()
    expect(screen.queryByRole('button', { name: sk.common.clearFilters })).toBeNull()
  })

  it('shows a subtle updating badge while refetching with data on screen', () => {
    renderCard({ status: { ...ok, isFetching: true } })
    expect(screen.getByText(sk.analytics.charts.updating)).toBeInTheDocument()
    expect(screen.getByTestId('chart')).toBeInTheDocument()
  })
})

describe('ChartCard table toggle and export', () => {
  it('swaps the graphic for a semantic table and back', () => {
    renderCard()
    const toggle = screen.getByRole('button', { name: sk.analytics.charts.showTable })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(toggle)
    expect(screen.getByRole('table', { name: 'Objem v čase' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Rok' })).toBeInTheDocument()
    expect(screen.queryByTestId('chart')).toBeNull()
    expect(screen.getByRole('button', { name: sk.analytics.charts.showChart })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: sk.analytics.charts.showChart }))
    expect(screen.getByTestId('chart')).toBeInTheDocument()
  })

  it('calls the CSV handler', () => {
    const onExportCsv = vi.fn()
    renderCard({ onExportCsv })
    fireEvent.click(screen.getByRole('button', { name: sk.analytics.charts.exportCsv }))
    expect(onExportCsv).toHaveBeenCalledTimes(1)
  })

  it('does not wrap semantic charts in an image role when asImage is false', () => {
    renderCard({ asImage: false })
    expect(screen.queryByRole('img')).toBeNull()
  })
})

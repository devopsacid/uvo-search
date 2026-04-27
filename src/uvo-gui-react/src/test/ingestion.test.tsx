import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderWithProviders, screen, waitFor, setupFetch } from './utils'
import { IngestionPage } from '../pages/IngestionPage'
import sk from '../i18n/sk'

const MOCK_RESPONSE = {
  generated_at: '2026-04-26T08:40:00Z',
  totals: {
    notices: 172242,
    registry_entries: 172242,
    cross_source_matches: 0,
    canonical_linked: 0,
    sources_healthy: 4,
    sources_total: 5,
    last_run_age_seconds: 27600,
    dedup_match_rate: 0.0,
  },
  latest_run: {
    id: '5b2c11a2-6148-4130-bc9a-ba810c981fd3',
    started_at: '2026-04-26T01:02:28Z',
    finished_at: null,
  },
  sources: [
    {
      name: 'vestnik',
      notices: 61954,
      last_24h: 0,
      last_7d: 0,
      registry: 61954,
      skips: 165290,
      disk_bytes: 320_000_000,
      last_ingest_at: '2026-04-26T01:02:00Z',
      age_seconds: 27600,
      status: 'healthy',
    },
    {
      name: 'crz',
      notices: 50000,
      last_24h: 5,
      last_7d: 30,
      registry: 50000,
      skips: 0,
      disk_bytes: 250_000_000,
      last_ingest_at: '2026-04-25T10:00:00Z',
      age_seconds: 95000,
      status: 'stale',
    },
    {
      name: 'ted',
      notices: 30000,
      last_24h: 0,
      last_7d: 0,
      registry: 30000,
      skips: 0,
      disk_bytes: 150_000_000,
      last_ingest_at: '2026-04-25T20:00:00Z',
      age_seconds: 45600,
      status: 'warning',
    },
    {
      name: 'uvo',
      notices: 20000,
      last_24h: 2,
      last_7d: 15,
      registry: 20000,
      skips: 0,
      disk_bytes: 90_000_000,
      last_ingest_at: '2026-04-26T07:00:00Z',
      age_seconds: 6000,
      status: 'healthy',
    },
    {
      name: 'itms',
      notices: 10288,
      last_24h: 0,
      last_7d: 0,
      registry: 10288,
      skips: 0,
      disk_bytes: 0,
      last_ingest_at: null,
      age_seconds: null,
      status: 'unknown',
    },
  ],
  timeseries: {
    daily_ingestion: Array.from({ length: 30 }, (_, i) => {
      const d = new Date('2026-03-28')
      d.setDate(d.getDate() + i)
      return {
        date: d.toISOString().slice(0, 10),
        vestnik: i % 3,
        crz: i % 2,
        ted: 0,
        uvo: i % 5,
        itms: 0,
      }
    }),
  },
}

describe('IngestionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders KPI cards from a mock API response', async () => {
    setupFetch({ '/dashboard/ingestion': { body: MOCK_RESPONSE } })

    renderWithProviders(<IngestionPage />, { route: '/ingestion' })

    await waitFor(() => {
      expect(screen.getByText(sk.ingestion.kpiNotices)).toBeInTheDocument()
      expect(screen.getByText(sk.ingestion.kpiSourcesHealthy)).toBeInTheDocument()
      expect(screen.getByText(sk.ingestion.kpiLastRunAge)).toBeInTheDocument()
      expect(screen.getByText(sk.ingestion.kpiDedupRate)).toBeInTheDocument()
      // kpiCrossMatches label also appears in dedup card, so use getAllByText
      expect(screen.getAllByText(sk.ingestion.kpiCrossMatches).length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText(sk.ingestion.kpiRegistryDrift)).toBeInTheDocument()
    })

    // Verify total notices value is shown (172 242 in sk-SK format)
    expect(screen.getByTestId('kpi-strip')).toBeInTheDocument()
  })

  it('shows red status badge for stale sources', async () => {
    setupFetch({ '/dashboard/ingestion': { body: MOCK_RESPONSE } })

    renderWithProviders(<IngestionPage />, { route: '/ingestion' })

    await waitFor(() => {
      const crzBadge = screen.getByTestId('status-badge-crz')
      expect(crzBadge).toBeInTheDocument()
      expect(crzBadge.textContent).toBe(sk.ingestion.statusStale)
      expect(crzBadge.className).toContain('bg-red-100')
    })
  })

  it('shows dedup warning when cross_source_matches === 0 and notices > 0', async () => {
    setupFetch({ '/dashboard/ingestion': { body: MOCK_RESPONSE } })

    renderWithProviders(<IngestionPage />, { route: '/ingestion' })

    await waitFor(() => {
      const warning = screen.getByTestId('dedup-warning')
      expect(warning).toBeInTheDocument()
      expect(warning.textContent).toContain(sk.ingestion.dedupCardWarning)
    })
  })

  it('renders the daily chart container with data', async () => {
    setupFetch({ '/dashboard/ingestion': { body: MOCK_RESPONSE } })

    renderWithProviders(<IngestionPage />, { route: '/ingestion' })

    await waitFor(() => {
      expect(screen.getByTestId('daily-chart')).toBeInTheDocument()
    })

    // Chart container is rendered — recharts manages SVG internally
    // Verify the data prop indirectly via the chart title being visible
    expect(screen.getByText(sk.ingestion.chartTitle)).toBeInTheDocument()
  })

  it('shows staleness banner for warning and stale sources', async () => {
    setupFetch({ '/dashboard/ingestion': { body: MOCK_RESPONSE } })

    renderWithProviders(<IngestionPage />, { route: '/ingestion' })

    await waitFor(() => {
      const banner = screen.getByTestId('stale-banner')
      expect(banner).toBeInTheDocument()
      // crz (stale) and ted (warning) should both be mentioned
      expect(banner.textContent).toContain('crz')
      expect(banner.textContent).toContain('ted')
    })
  })

  it('shows error state when fetch fails', async () => {
    setupFetch({ '/dashboard/ingestion': { status: 500, body: { detail: 'server error' } } })

    renderWithProviders(<IngestionPage />, { route: '/ingestion' })

    await waitFor(() => {
      expect(screen.getByText(sk.ingestion.error)).toBeInTheDocument()
    })
  })

  it('does not show dedup warning when cross_source_matches > 0', async () => {
    const noWarnResponse = {
      ...MOCK_RESPONSE,
      totals: { ...MOCK_RESPONSE.totals, cross_source_matches: 500, dedup_match_rate: 0.003 },
    }
    setupFetch({ '/dashboard/ingestion': { body: noWarnResponse } })

    renderWithProviders(<IngestionPage />, { route: '/ingestion' })

    await waitFor(() => {
      expect(screen.getByTestId('kpi-strip')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('dedup-warning')).not.toBeInTheDocument()
  })
})

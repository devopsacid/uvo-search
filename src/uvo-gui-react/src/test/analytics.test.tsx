import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor } from './utils'
import { DateRangePicker } from '../components/ui/DateRangePicker'
import { HhiGauge } from '../components/charts/HhiGauge'
import { ProcurerAnalyticsPage } from '../pages/analytics/ProcurerAnalyticsPage'
import { SupplierAnalyticsPage } from '../pages/analytics/SupplierAnalyticsPage'
import { ExecutiveSummaryPage } from '../pages/analytics/ExecutiveSummaryPage'
import sk from '../i18n/sk'

// ── Shared fixture ────────────────────────────────────────────────────────────

const periodSummary = {
  ico: '12345678',
  name: 'Testova firma',
  entity_type: 'procurer',
  period: {
    date_from: '2025-01-01',
    date_to: '2026-01-01',
    prior_date_from: '2024-01-01',
    prior_date_to: '2025-01-01',
  },
  kpis: {
    total_value: 5_000_000,
    contract_count: 42,
    avg_value: 119048,
    unique_counterparties: 8,
    value_coverage: 0.92,
    deltas: {
      total_value_pct: 12.5,
      contract_count_pct: 5.0,
      avg_value_pct: null,
      unique_counterparties_pct: -10.0,
    },
  },
  monthly_spend: [
    { month: '2025-01', total_value: 400_000, contract_count: 3 },
    { month: '2025-02', total_value: 350_000, contract_count: 4 },
  ],
  top_counterparties: [
    { ico: '87654321', name: 'Dodavatel A', total_value: 2_000_000, contract_count: 15, share_pct: 0.4 },
  ],
  cpv_breakdown: [
    { cpv_code: '72000000', label_sk: 'IT sluzby', label_en: 'IT services', total_value: 3_000_000, contract_count: 20, share_pct: 0.6 },
  ],
  concentration: {
    hhi: 0.18,
    top1_share_pct: 0.4,
    top3_share_pct: 0.75,
  },
}

const executiveSummary = {
  ...periodSummary,
  anomalies: [
    {
      code: 'HIGH_CONCENTRATION',
      severity: 'warn',
      title_sk: 'Vysoka koncentracia',
      detail_sk: 'Top 3 dodavatelia tvoria 75% objemu.',
      metric_value: 75,
    },
  ],
}

function mockFetch(urlResponseMap: Record<string, unknown>) {
  global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    const key = Object.keys(urlResponseMap).find((k) => url.includes(k))
    if (!key) {
      return { ok: false, status: 404, json: async () => ({}) } as Response
    }
    return { ok: true, status: 200, json: async () => urlResponseMap[key] } as Response
  }) as typeof fetch
}

// ── DateRangePicker ───────────────────────────────────────────────────────────

describe('DateRangePicker', () => {
  it('renders date inputs and preset buttons', () => {
    renderWithProviders(<DateRangePicker />, {
      route: '/analytics/procurer/12345678?date_from=2025-01-01&date_to=2026-01-01',
    })
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(4)
    expect(screen.getByDisplayValue('2025-01-01')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2026-01-01')).toBeInTheDocument()
  })

  it('highlights the active last-12m preset when params match', () => {
    const today = new Date().toISOString().slice(0, 10)
    const d = new Date()
    d.setDate(d.getDate() - 365)
    const from = d.toISOString().slice(0, 10)

    renderWithProviders(<DateRangePicker />, {
      route: `/analytics/procurer/12345678?date_from=${from}&date_to=${today}`,
    })

    const activeBtn = screen.getByText(sk.analytics.common.preset12m)
    expect(activeBtn.className).toContain('bg-primary')
  })

  it('renders all four preset labels', () => {
    renderWithProviders(<DateRangePicker />)
    expect(screen.getByText(sk.analytics.common.preset30d)).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.common.preset12m)).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.common.presetYtd)).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.common.presetPrevYear)).toBeInTheDocument()
  })
})

// ── HhiGauge ─────────────────────────────────────────────────────────────────

describe('HhiGauge', () => {
  it('shows green label for low HHI (< 0.15)', () => {
    renderWithProviders(<HhiGauge hhi={0.08} />)
    const el = screen.getByText(sk.analytics.common.hhiLow)
    expect(el).toBeInTheDocument()
    expect(el.className).toContain('text-green')
  })

  it('shows amber label for medium HHI (0.15-0.4)', () => {
    renderWithProviders(<HhiGauge hhi={0.2} />)
    const el = screen.getByText(sk.analytics.common.hhiMedium)
    expect(el).toBeInTheDocument()
    expect(el.className).toContain('text-amber')
  })

  it('shows red label for high HHI (>= 0.4)', () => {
    renderWithProviders(<HhiGauge hhi={0.55} />)
    const el = screen.getByText(sk.analytics.common.hhiHigh)
    expect(el).toBeInTheDocument()
    expect(el.className).toContain('text-red')
  })

  it('renders numeric HHI value in SVG text on 0-10000 scale', () => {
    renderWithProviders(<HhiGauge hhi={0.1234} />)
    expect(screen.getByText('1234')).toBeInTheDocument()
  })

  it('renders top1 and top3 share when provided', () => {
    renderWithProviders(<HhiGauge hhi={0.15} top1SharePct={0.4} top3SharePct={0.75} />)
    expect(screen.getByText(/40\.0/)).toBeInTheDocument()
    expect(screen.getByText(/75\.0/)).toBeInTheDocument()
  })
})

// ── ProcurerAnalyticsPage ─────────────────────────────────────────────────────

describe('ProcurerAnalyticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch({ '/procurers/12345678/period-summary': periodSummary })
  })

  it('renders entity name from API', async () => {
    renderWithProviders(<ProcurerAnalyticsPage />, {
      route: '/analytics/procurer/12345678',
      routePattern: '/analytics/procurer/:ico',
    })
    await waitFor(() => {
      expect(screen.getByText('Testova firma')).toBeInTheDocument()
    })
  })

  it('renders KPI labels', async () => {
    renderWithProviders(<ProcurerAnalyticsPage />, {
      route: '/analytics/procurer/12345678',
      routePattern: '/analytics/procurer/:ico',
    })
    await waitFor(() => {
      expect(screen.getAllByText(sk.analytics.procurer.kpiSpend).length).toBeGreaterThan(0)
      expect(screen.getAllByText(sk.analytics.procurer.kpiContracts).length).toBeGreaterThan(0)
    })
  })

  it('shows value-coverage subtext when coverage < 1', async () => {
    renderWithProviders(<ProcurerAnalyticsPage />, {
      route: '/analytics/procurer/12345678',
      routePattern: '/analytics/procurer/:ico',
    })
    await waitFor(() => {
      expect(screen.getByText(/92.*kontraktov/)).toBeInTheDocument()
    })
  })

  it('renders top counterparty name', async () => {
    renderWithProviders(<ProcurerAnalyticsPage />, {
      route: '/analytics/procurer/12345678',
      routePattern: '/analytics/procurer/:ico',
    })
    await waitFor(() => {
      expect(screen.getAllByText('Dodavatel A').length).toBeGreaterThan(0)
    })
  })

  it('shows error state on fetch failure', async () => {
    global.fetch = vi.fn(async () =>
      ({ ok: false, status: 500, json: async () => ({}) } as unknown as Response),
    ) as typeof fetch

    renderWithProviders(<ProcurerAnalyticsPage />, {
      route: '/analytics/procurer/12345678',
      routePattern: '/analytics/procurer/:ico',
    })
    await waitFor(() => {
      expect(screen.getByText(sk.analytics.common.error)).toBeInTheDocument()
    })
  })
})

// ── SupplierAnalyticsPage ─────────────────────────────────────────────────────

describe('SupplierAnalyticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch({ '/suppliers/12345678/period-summary': { ...periodSummary, entity_type: 'supplier' } })
  })

  it('renders entity name from API', async () => {
    renderWithProviders(<SupplierAnalyticsPage />, {
      route: '/analytics/supplier/12345678',
      routePattern: '/analytics/supplier/:ico',
    })
    await waitFor(() => {
      expect(screen.getByText('Testova firma')).toBeInTheDocument()
    })
  })

  it('renders procurer section label', async () => {
    renderWithProviders(<SupplierAnalyticsPage />, {
      route: '/analytics/supplier/12345678',
      routePattern: '/analytics/supplier/:ico',
    })
    await waitFor(() => {
      expect(screen.getByText(sk.analytics.supplier.sectionProcurers)).toBeInTheDocument()
    })
  })
})

// ── ExecutiveSummaryPage ──────────────────────────────────────────────────────

describe('ExecutiveSummaryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch({ '/companies/12345678/executive-summary': executiveSummary })
  })

  it('renders entity name', async () => {
    renderWithProviders(<ExecutiveSummaryPage />, {
      route: '/analytics/executive/12345678?entity_type=procurer',
      routePattern: '/analytics/executive/:ico',
    })
    await waitFor(() => {
      expect(screen.getByText('Testova firma')).toBeInTheDocument()
    })
  })

  it('renders anomaly banner for warn severity', async () => {
    renderWithProviders(<ExecutiveSummaryPage />, {
      route: '/analytics/executive/12345678?entity_type=procurer',
      routePattern: '/analytics/executive/:ico',
    })
    await waitFor(() => {
      expect(screen.getByText('Vysoka koncentracia')).toBeInTheDocument()
    })
  })

  it('renders entity type toggle buttons', () => {
    renderWithProviders(<ExecutiveSummaryPage />, {
      route: '/analytics/executive/12345678?entity_type=procurer',
      routePattern: '/analytics/executive/:ico',
    })
    expect(screen.getByText(sk.analytics.executive.toggleProcurer)).toBeInTheDocument()
    expect(screen.getByText(sk.analytics.executive.toggleSupplier)).toBeInTheDocument()
  })
})

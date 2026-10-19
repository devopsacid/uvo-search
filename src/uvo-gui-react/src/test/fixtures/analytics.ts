/**
 * One fixture per `/api/analytics/*` endpoint, shaped exactly like the contract in
 * docs/specs/2026-10-19-analytics-dashboards.md §6.2 (key names are the contract).
 */
import type {
  AnalyticsConcentration,
  AnalyticsCoverage,
  AnalyticsCpv,
  AnalyticsMeta,
  AnalyticsSummary,
  AnalyticsTimeseries,
  AnalyticsTop,
} from '@/api/types'

export const meta: AnalyticsMeta = {
  definition: 'D1',
  filters: {
    date_from: '2022-01-01',
    date_to: '2026-10-19',
    cpv: null,
    source: null,
    procurer_ico: null,
    supplier_ico: null,
  },
  generated_at: '2026-10-19T10:00:00Z',
}

export const summaryFixture: AnalyticsSummary = {
  meta,
  current: {
    date_from: '2022-01-01',
    date_to: '2026-10-19',
    contract_count: 1200,
    total_value: 4_200_000_000,
    avg_value: 3_500_000,
    procurer_count: 310,
    supplier_count: 890,
  },
  previous: {
    date_from: '2017-01-01',
    date_to: '2021-12-31',
    contract_count: 1000,
    total_value: 3_800_000_000,
    avg_value: 3_800_000,
    procurer_count: 280,
    supplier_count: 700,
  },
  deltas: {
    contract_count_pct: 20,
    total_value_pct: 10.5,
    avg_value_pct: -7.9,
    procurer_count_pct: 10.7,
    supplier_count_pct: null,
  },
}

export const timeseriesFixture: AnalyticsTimeseries = {
  meta,
  granularity: 'year',
  points: [
    { period: '2022', contract_count: 200, total_value: 700_000_000, avg_value: 3_500_000 },
    { period: '2023', contract_count: 300, total_value: 1_200_000_000, avg_value: 4_000_000 },
    { period: '2024', contract_count: 250, total_value: 900_000_000, avg_value: 3_600_000 },
  ],
  series: null,
}

export const timeseriesByCpvFixture: AnalyticsTimeseries = {
  ...timeseriesFixture,
  series: [
    {
      key: '45000000',
      label: 'Stavebné práce',
      points: [
        { period: '2022', contract_count: 100, total_value: 400_000_000, avg_value: 4_000_000 },
        { period: '2023', contract_count: 120, total_value: 600_000_000, avg_value: 5_000_000 },
      ],
    },
    {
      key: 'other',
      label: 'Ostatné',
      points: [
        { period: '2022', contract_count: 100, total_value: 300_000_000, avg_value: 3_000_000 },
        { period: '2023', contract_count: 180, total_value: 600_000_000, avg_value: 3_333_333 },
      ],
    },
  ],
}

export const topSuppliersFixture: AnalyticsTop = {
  meta,
  dimension: 'supplier',
  metric: 'total_value',
  total: { total_value: 4_200_000_000, contract_count: 1200 },
  items: [
    { key: '36396567', label: 'Skanska SK', ico: '36396567', total_value: 900_000_000, contract_count: 40, share_pct: 21.4 },
    { key: '35742346', label: 'Doprastav', ico: '35742346', total_value: 600_000_000, contract_count: 25, share_pct: 14.3 },
  ],
  other: { total_value: 2_700_000_000, contract_count: 1135, share_pct: 64.3 },
}

export const topProcurersFixture: AnalyticsTop = {
  ...topSuppliersFixture,
  dimension: 'procurer',
  items: [
    { key: '00151742', label: 'Slovenská správa ciest', ico: '00151742', total_value: 800_000_000, contract_count: 30, share_pct: 19 },
    { key: '17316219', label: 'Národná diaľničná spoločnosť', ico: '17316219', total_value: 500_000_000, contract_count: 12, share_pct: 11.9 },
  ],
  other: { total_value: 2_900_000_000, contract_count: 1158, share_pct: 69.1 },
}

export const concentrationFixture: AnalyticsConcentration = {
  meta,
  dimension: 'supplier',
  hhi: 1820.4,
  hhi_band: 'moderate',
  cr4_pct: 48.2,
  cr10_pct: 71.9,
  entity_count: 890,
  total_value: 4_200_000_000,
  top: [
    { ico: '36396567', name: 'Skanska SK', total_value: 900_000_000, share_pct: 21.4, cumulative_pct: 21.4 },
    { ico: '35742346', name: 'Doprastav', total_value: 600_000_000, share_pct: 14.3, cumulative_pct: 35.7 },
    { ico: '31337003', name: 'Strabag', total_value: 400_000_000, share_pct: 9.5, cumulative_pct: 45.2 },
  ],
}

export const cpvFixture: AnalyticsCpv = {
  meta,
  level: 'division',
  total_value: 4_200_000_000,
  contract_count: 1200,
  items: [
    { cpv_code: '45000000', prefix: '45', label_sk: 'Stavebné práce', total_value: 2_000_000_000, contract_count: 500, share_pct: 47.6 },
    { cpv_code: '33000000', prefix: '33', label_sk: 'Zdravotnícke zariadenia', total_value: 700_000_000, contract_count: 150, share_pct: 16.7 },
    { cpv_code: '00000000', prefix: '00', label_sk: 'Bez CPV', total_value: 100_000_000, contract_count: 20, share_pct: 2.4 },
  ],
}

export const coverageFixture: AnalyticsCoverage = {
  generated_at: '2026-10-19T10:00:00Z',
  sources: [
    {
      source: 'vestnik',
      notices_total: 500_000,
      contract_awards: 120_000,
      last_publication_date: '2026-10-18',
      last_ingested_at: '2026-10-19T08:00:00Z',
      age_seconds: 7200,
      status: 'healthy',
      expected_cadence_seconds: 3600,
      quality: { with_value_pct: 82.5, with_cpv_pct: 97.1, with_supplier_ico_pct: 71, with_procurer_ico_pct: 99.2 },
    },
    {
      source: 'uvo',
      notices_total: 10_000,
      contract_awards: 8_000,
      last_publication_date: '2019-05-01',
      last_ingested_at: null,
      age_seconds: null,
      status: 'legacy',
      expected_cadence_seconds: null,
      quality: { with_value_pct: 60, with_cpv_pct: 90, with_supplier_ico_pct: 50, with_procurer_ico_pct: 95 },
    },
  ],
  monthly: [
    { period: '2026-08', vestnik: 1200, crz: 800, ted: 90, uvo: 0, itms: 40 },
    { period: '2026-09', vestnik: 1100, crz: 760, ted: 85, uvo: 0, itms: 55 },
  ],
  canonical: { notices_with_canonical_id: 3400, match_groups: 1500 },
}

/** Responses keyed by a URL fragment, for `setupFetch` (more specific keys first). */
export const analyticsResponses = {
  '/analytics/summary': { body: summaryFixture },
  '/analytics/timeseries': { body: timeseriesFixture },
  '/analytics/top?': { body: topSuppliersFixture },
  '/analytics/concentration': { body: concentrationFixture },
  '/analytics/cpv': { body: cpvFixture },
  '/analytics/coverage': { body: coverageFixture },
  '/contracts': {
    body: {
      data: [
        {
          id: 'c-1',
          title: 'Rekonštrukcia cesty I/18',
          procurer_ico: '00151742',
          procurer_name: 'Slovenská správa ciest',
          supplier_ico: '36396567',
          supplier_name: 'Skanska SK',
          value: 12_500_000,
          year: 2024,
          status: 'completed',
          cpv_code: '45233120',
        },
      ],
      pagination: { total: 1, limit: 8, offset: 0 },
    },
  },
}

/**
 * A fetch stub for tests that render pages: routes by endpoint, procurer/supplier `top`
 * by the `dimension` param. Records every requested URL in `calls`.
 */
export function makeAnalyticsFetch(overrides: Partial<Record<string, { status?: number; body: unknown }>> = {}) {
  const calls: string[] = []
  const impl = async (input: RequestInfo | URL): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    calls.push(url)
    const u = new URL(url, 'http://localhost')
    const path = u.pathname
    let res: { status?: number; body: unknown } | undefined
    for (const [fragment, value] of Object.entries(overrides)) {
      if (value && url.includes(fragment)) {
        res = value
        break
      }
    }
    if (!res) {
      if (path.endsWith('/analytics/summary')) res = { body: summaryFixture }
      else if (path.endsWith('/analytics/timeseries'))
        res = { body: u.searchParams.get('split_by') ? timeseriesByCpvFixture : timeseriesFixture }
      else if (path.endsWith('/analytics/top'))
        res = { body: u.searchParams.get('dimension') === 'procurer' ? topProcurersFixture : topSuppliersFixture }
      else if (path.endsWith('/analytics/concentration')) res = { body: concentrationFixture }
      else if (path.endsWith('/analytics/cpv')) res = { body: cpvFixture }
      else if (path.endsWith('/analytics/coverage')) res = { body: coverageFixture }
      else if (path.endsWith('/search/entities')) res = { body: { items: [] } }
      else if (path.includes('/contracts')) res = analyticsResponses['/contracts']
      else res = { status: 404, body: { detail: 'not found' } }
    }
    return {
      ok: (res.status ?? 200) < 400,
      status: res.status ?? 200,
      json: async () => res.body,
    } as Response
  }
  return { impl: impl as typeof fetch, calls }
}

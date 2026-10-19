import { describe, it, expect, vi, afterEach } from 'vitest'
import { createQueryClient, shouldRetry } from '@/api/queryClient'
import { apiClient } from '@/api/client'
import { dashboardKeys } from '@/api/queries/dashboard'
import { companyKeys } from '@/api/queries/companies'
import { ingestionKeys } from '@/api/queries/ingestion'

describe('createQueryClient', () => {
  it('disables refetch on window focus', () => {
    const qc = createQueryClient()
    expect(qc.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(false)
  })

  it('does not retry 4xx errors but retries one transient failure', () => {
    expect(shouldRetry(0, Object.assign(new Error('x'), { status: 404 }))).toBe(false)
    expect(shouldRetry(0, Object.assign(new Error('x'), { status: 422 }))).toBe(false)
    expect(shouldRetry(0, Object.assign(new Error('x'), { status: 503 }))).toBe(true)
    expect(shouldRetry(0, new Error('network'))).toBe(true)
    expect(shouldRetry(1, new Error('network'))).toBe(false)
  })

  it('gives aggregate dashboard queries a longer staleTime than the default', () => {
    const qc = createQueryClient()
    const def = qc.getDefaultOptions().queries?.staleTime as number
    const agg = qc.getQueryDefaults(dashboardKeys.summary()).staleTime as number
    expect(agg).toBeGreaterThan(def)
  })

  it('accepts overrides for tests', () => {
    const qc = createQueryClient({ retry: false, staleTime: Infinity })
    expect(qc.getDefaultOptions().queries?.retry).toBe(false)
  })
})

describe('query key factories', () => {
  it('share a root so invalidating by prefix works', () => {
    expect(companyKeys.profile('1')).toEqual([...companyKeys.all, 'profile', '1'])
    expect(companyKeys.list({ q: 'a' })[0]).toBe(companyKeys.all[0])
    expect(ingestionKeys.log({}).slice(0, 1)).toEqual(ingestionKeys.all)
    expect(ingestionKeys.workerStatus().slice(0, 1)).toEqual(ingestionKeys.all)
  })
})

describe('apiClient AbortSignal', () => {
  afterEach(() => vi.restoreAllMocks())

  it('forwards the signal to fetch', async () => {
    const fetchMock = vi.fn(
      async (_url: unknown, _init?: RequestInit) =>
        ({ ok: true, status: 200, json: async () => ({}) }) as Response,
    )
    global.fetch = fetchMock as unknown as typeof fetch
    const ctrl = new AbortController()
    await apiClient.get('/x', { signal: ctrl.signal })
    expect(fetchMock.mock.calls[0][1]?.signal).toBe(ctrl.signal)
  })
})

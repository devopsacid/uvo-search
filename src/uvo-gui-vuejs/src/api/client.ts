const BASE = '/api'

async function get<T>(path: string, params: Record<string, string | number | null | undefined> = {}): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined) url.searchParams.set(k, String(v))
  })
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json() as Promise<T>
}

export interface DashboardSummary {
  total_value: number
  contract_count: number
  avg_value: number
  active_suppliers: number
  deltas: Record<string, { value: number; pct?: number }>
}

export interface SpendByYear { year: number; total_value: number }
export interface TopSupplier { ico: string; name: string; total_value: number; contract_count: number }
export interface TopProcurer { ico: string; name: string; total_spend: number; contract_count: number }
export interface CpvShare { cpv_code: string; label_sk: string; label_en: string; total_value: number; percentage: number }
export interface RecentContract { id: string; title: string; procurer_name: string; procurer_ico: string; value: number; year: number; status: string }

export interface ContractRow { id: string; title: string; procurer_name: string; procurer_ico: string; supplier_name: string | null; supplier_ico: string | null; value: number; cpv_code: string | null; year: number; status: string }
export interface ContractDetail extends ContractRow { all_suppliers: Record<string, string>[]; publication_date: string | null }
export interface Pagination { total: number; limit: number; offset: number }
export interface ContractListResponse { data: ContractRow[]; pagination: Pagination }

export interface EntityCard { ico: string; name: string; contract_count: number; total_value?: number; total_spend?: number }
export interface EntityListResponse { data: EntityCard[]; pagination: Pagination }

export interface EntitySummary { ico: string; name: string; contract_count: number; total_value?: number; total_spend?: number; avg_value: number; spend_by_year: SpendByYear[] }

export interface EntityHit { ico: string; name: string; type: 'supplier' | 'procurer'; contract_count: number; total_value: number }
export interface EntitySearchResponse { items: EntityHit[] }

export const api = {
  dashboard: {
    summary: (p = {}) => get<DashboardSummary>('/dashboard/summary', p),
    spendByYear: (p = {}) => get<SpendByYear[]>('/dashboard/spend-by-year', p),
    topSuppliers: (p = {}) => get<TopSupplier[]>('/dashboard/top-suppliers', p),
    topProcurers: (p = {}) => get<TopProcurer[]>('/dashboard/top-procurers', p),
    byCpv: (p = {}) => get<CpvShare[]>('/dashboard/by-cpv', p),
    recent: (p = {}) => get<RecentContract[]>('/dashboard/recent', p),
  },
  contracts: {
    list: (p = {}) => get<ContractListResponse>('/contracts', p),
    detail: (id: string) => get<ContractDetail>(`/contracts/${id}`),
  },
  suppliers: {
    list: (p = {}) => get<EntityListResponse>('/suppliers', p),
    detail: (ico: string) => get<Record<string, unknown>>(`/suppliers/${ico}`),
    summary: (ico: string) => get<EntitySummary>(`/suppliers/${ico}/summary`),
  },
  procurers: {
    list: (p = {}) => get<EntityListResponse>('/procurers', p),
    detail: (ico: string) => get<Record<string, unknown>>(`/procurers/${ico}`),
    summary: (ico: string) => get<EntitySummary>(`/procurers/${ico}/summary`),
  },
  search: {
    entities: (q: string, limit = 10) => get<EntitySearchResponse>('/search/entities', { q, limit }),
  },
}

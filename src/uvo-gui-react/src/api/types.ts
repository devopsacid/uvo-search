// ── Shared ────────────────────────────────────────────────────────────────────

export interface PaginationMeta {
  total: number
  limit: number
  offset: number
}

// ── Dashboard (Phase 1) ───────────────────────────────────────────────────────

export interface DashboardDelta {
  value: number
  pct: number | null
}

export interface DashboardSummary {
  total_value: number
  contract_count: number
  avg_value: number
  active_suppliers: number
  deltas: Record<string, DashboardDelta>
}

export interface SpendByYear {
  year: number
  total_value: number
}

export interface TopSupplier {
  ico: string
  name: string
  total_value: number
  contract_count: number
}

export interface TopProcurer {
  ico: string
  name: string
  total_spend: number
  contract_count: number
}

export interface RecentContract {
  id: string
  title: string
  procurer_name: string
  procurer_ico: string
  value: number
  year: number
  status: string
}

// ── Contracts ─────────────────────────────────────────────────────────────────

export interface ContractRow {
  id: string
  title: string
  procurer_name: string
  procurer_ico: string
  supplier_name: string | null
  supplier_ico: string | null
  value: number
  cpv_code: string | null
  year: number
  status: string
}

export interface ContractDetail extends ContractRow {
  all_suppliers: Record<string, unknown>[]
  publication_date: string | null
}

export interface ContractListResponse {
  data: ContractRow[]
  pagination: PaginationMeta
}

// ── Suppliers ─────────────────────────────────────────────────────────────────

export interface SupplierCard {
  ico: string
  name: string
  contract_count: number
  total_value: number
}

export interface SupplierListResponse {
  data: SupplierCard[]
  pagination: PaginationMeta
}

export interface ProcurerRelation {
  ico: string
  name: string
  contract_count: number
  total_value: number
}

export interface SupplierDetail {
  ico: string
  name: string
  contract_count: number
  total_value: number
  avg_value: number
  years_active: number[]
  top_procurers: ProcurerRelation[]
  contracts: ContractRow[]
}

export interface SupplierSummary {
  ico: string
  name: string
  contract_count: number
  total_value: number
  avg_value: number
  spend_by_year: SpendByYear[]
}

// ── Procurers ─────────────────────────────────────────────────────────────────

export interface ProcurerCard {
  ico: string
  name: string
  contract_count: number
  total_spend: number // note: field name differs from SupplierCard.total_value
}

export interface ProcurerListResponse {
  data: ProcurerCard[]
  pagination: PaginationMeta
}

export interface SupplierRelation {
  ico: string
  name: string
  contract_count: number
  total_value: number
}

export interface ProcurerDetail {
  ico: string
  name: string
  contract_count: number
  total_spend: number
  avg_value: number
  years_active: number[]
  top_suppliers: SupplierRelation[]
  contracts: ContractRow[]
}

export interface ProcurerSummary {
  ico: string
  name: string
  contract_count: number
  total_spend: number
  avg_value: number
  spend_by_year: SpendByYear[]
}

// ── Search / autocomplete ─────────────────────────────────────────────────────

export interface EntityHit {
  ico: string
  name: string
  type: 'supplier' | 'procurer'
  contract_count: number
  total_value: number
}

export interface EntitySearchResponse {
  items: EntityHit[]
}

// ── Dashboard Phase 3 ─────────────────────────────────────────────────────────

export interface CpvShare {
  cpv_code: string
  label_sk: string
  label_en: string
  total_value: number
  percentage: number
}

export interface MonthBucket {
  month: number // 1..12
  contract_count: number
  total_value: number
}

// ── Concentration ─────────────────────────────────────────────────────────────

export interface SupplierShare {
  ico: string
  name: string
  total_value: number
  share: number // 0..100
}

export interface ConcentrationResponse {
  procurer_ico: string
  procurer_name: string
  top_suppliers: SupplierShare[]
  hhi: number // 0..10000
}

// ── Graph (Cytoscape-compatible) ───────────────────────────────────────────────

export interface CytoNodeData {
  id: string
  label: string
  type: string // 'procurer' | 'supplier'
  value: number
}

export interface CytoEdgeData {
  id: string
  source: string
  target: string
  label: string
  value: number
}

export interface CytoNode {
  data: CytoNodeData
}

export interface CytoEdge {
  data: CytoEdgeData
}

export interface GraphResponse {
  nodes: CytoNode[]
  edges: CytoEdge[]
}

// ── Shared error ──────────────────────────────────────────────────────────────

export interface ApiError {
  status: number
  message: string
}

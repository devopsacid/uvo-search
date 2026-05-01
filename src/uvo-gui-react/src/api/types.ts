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

// ── Ingestion Dashboard ───────────────────────────────────────────────────────

export type IngestionSourceStatus = 'healthy' | 'warning' | 'stale' | 'unknown'

export interface IngestionSource {
  name: string
  notices: number
  last_24h: number
  last_7d: number
  registry: number
  skips: number
  disk_bytes: number
  last_ingest_at: string | null
  age_seconds: number | null
  status: IngestionSourceStatus
}

export interface IngestionTotals {
  notices: number
  registry_entries: number
  cross_source_matches: number
  canonical_linked: number
  sources_healthy: number
  sources_total: number
  last_run_age_seconds: number | null
  dedup_match_rate: number
}

export interface IngestionLatestRun {
  id: string | null
  started_at: string | null
  finished_at: string | null
}

export interface DailyIngestionBucket {
  date: string
  vestnik: number
  crz: number
  ted: number
  uvo: number
  itms: number
}

export interface IngestionDashboard {
  generated_at: string
  totals: IngestionTotals
  latest_run: IngestionLatestRun
  sources: IngestionSource[]
  timeseries: {
    daily_ingestion: DailyIngestionBucket[]
  }
}

// ── Analytics (period summary + executive summary) ────────────────────────────

export interface PeriodDeltas {
  total_value_pct: number | null
  contract_count_pct: number | null
  avg_value_pct: number | null
  unique_counterparties_pct: number | null
}

export interface PeriodKpis {
  total_value: number
  contract_count: number
  avg_value: number
  unique_counterparties: number
  value_coverage: number
  deltas: PeriodDeltas
}

export interface MonthlySpendBucket {
  month: string // YYYY-MM
  total_value: number
  contract_count: number
}

export interface CounterpartyRow {
  ico: string | null
  name: string
  total_value: number
  contract_count: number
  share_pct: number
}

export interface CpvBreakdownRow {
  cpv_code: string
  label_sk: string | null
  label_en: string | null
  total_value: number
  contract_count: number
  share_pct: number
}

export interface ConcentrationBlock {
  hhi: number
  top1_share_pct: number
  top3_share_pct: number
}

export interface PeriodMeta {
  date_from: string
  date_to: string
  prior_date_from: string
  prior_date_to: string
}

export interface PeriodSummary {
  ico: string
  name: string
  entity_type: 'procurer' | 'supplier'
  period: PeriodMeta
  kpis: PeriodKpis
  monthly_spend: MonthlySpendBucket[]
  top_counterparties: CounterpartyRow[]
  cpv_breakdown: CpvBreakdownRow[]
  concentration: ConcentrationBlock
}

export type AnomalySeverity = 'info' | 'warn' | 'critical'

export interface Anomaly {
  code: string
  severity: AnomalySeverity
  title_sk: string
  detail_sk: string
  metric_value: number | null
}

export interface ExecutiveSummary extends PeriodSummary {
  anomalies: Anomaly[]
}

// ── Shared error ──────────────────────────────────────────────────────────────

export interface ApiError {
  status: number
  message: string
}

// ── Ingestion log ─────────────────────────────────────────────────────────────

export type IngestionLogLevel = 'info' | 'warning' | 'error' | 'critical'

export interface IngestionLogItem {
  ts: string
  level: IngestionLogLevel
  event: string
  component: string
  source: string | null
  source_id: string | null
  instance_id: string | null
  pipeline_run_id: string | null
  message: string
  details: Record<string, unknown>
}

export interface IngestionLogResponse {
  total: number
  items: IngestionLogItem[]
}

// ── Worker status ─────────────────────────────────────────────────────────────

export type WorkerStatusValue = 'healthy' | 'stale' | 'stopped' | 'error' | 'unknown'

export interface WorkerStatus {
  component: string
  name: string
  status: WorkerStatusValue
  last_event: string | null
  last_level: string | null
  last_message: string | null
  last_ts: string | null
  age_seconds: number | null
  events_24h: number
}

export interface WorkerStatusResponse {
  workers: WorkerStatus[]
  generated_at: string
}

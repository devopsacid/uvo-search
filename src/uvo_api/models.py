# src/uvo_api/models.py
"""Pydantic v2 response models for the analytics API."""

from pydantic import BaseModel

# --- Shared ---


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


# --- Dashboard ---


class DashboardDelta(BaseModel):
    value: float
    pct: float | None = None  # percentage change vs. previous year


class DashboardSummary(BaseModel):
    total_value: float
    contract_count: int
    avg_value: float
    active_suppliers: int
    deltas: dict[str, DashboardDelta] = {}


class SpendByYear(BaseModel):
    year: int
    total_value: float


class TopSupplier(BaseModel):
    ico: str
    name: str
    total_value: float
    contract_count: int


class TopProcurer(BaseModel):
    ico: str
    name: str
    total_spend: float
    contract_count: int


class CpvShare(BaseModel):
    cpv_code: str
    label_sk: str
    label_en: str
    total_value: float
    percentage: float


class RecentContract(BaseModel):
    id: str
    title: str
    procurer_name: str
    procurer_ico: str
    value: float
    year: int
    status: str  # "active" | "closed"


# --- Contracts ---


class ContractRow(BaseModel):
    id: str
    title: str
    procurer_name: str
    procurer_ico: str
    supplier_name: str | None = None
    supplier_ico: str | None = None
    value: float
    cpv_code: str | None = None
    year: int
    status: str


class ContractDetail(ContractRow):
    all_suppliers: list[dict] = []
    publication_date: str | None = None


class ContractListResponse(BaseModel):
    data: list[ContractRow]
    pagination: PaginationMeta


# --- Suppliers ---


class SupplierCard(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float


class SupplierListResponse(BaseModel):
    data: list[SupplierCard]
    pagination: PaginationMeta


class ProcurerRelation(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float


class SupplierDetail(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float
    avg_value: float
    years_active: list[int]
    top_procurers: list[ProcurerRelation]
    contracts: list[ContractRow]


class SupplierSummary(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float
    avg_value: float
    spend_by_year: list[SpendByYear]


# --- Procurers ---


class ProcurerCard(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_spend: float


class ProcurerListResponse(BaseModel):
    data: list[ProcurerCard]
    pagination: PaginationMeta


class SupplierRelation(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float


class ProcurerDetail(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_spend: float
    avg_value: float
    years_active: list[int]
    top_suppliers: list[SupplierRelation]
    contracts: list[ContractRow]


class ProcurerSummary(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_spend: float
    avg_value: float
    spend_by_year: list[SpendByYear]


# --- Dashboard extensions (Phase 3) ---


class MonthBucket(BaseModel):
    month: int  # 1..12
    contract_count: int
    total_value: float


# --- Concentration ---


class SupplierShare(BaseModel):
    ico: str
    name: str
    total_value: float
    share: float  # 0..100 percentage


class ConcentrationResponse(BaseModel):
    procurer_ico: str
    procurer_name: str
    top_suppliers: list[SupplierShare]
    hhi: float  # Herfindahl-Hirschman Index 0..10000


# --- Ingestion dashboard ---


class IngestionSourceStatus(BaseModel):
    name: str
    notices: int
    last_24h: int
    last_7d: int
    registry: int
    skips: int
    disk_bytes: int  # sum of BSON document sizes for this source's notices
    last_ingest_at: str | None  # ISO 8601 UTC with Z, or null
    age_seconds: float | None
    status: str  # "healthy" | "warning" | "stale" | "unknown"


class IngestionTotals(BaseModel):
    notices: int
    registry_entries: int
    cross_source_matches: int
    canonical_linked: int
    sources_healthy: int
    sources_total: int
    last_run_age_seconds: float | None
    dedup_match_rate: float


class IngestionLatestRun(BaseModel):
    id: str | None
    started_at: str | None  # ISO 8601 UTC with Z, or null
    finished_at: str | None  # always null (not tracked)


class DailyBucket(BaseModel):
    date: str  # YYYY-MM-DD
    vestnik: int
    crz: int
    ted: int
    uvo: int
    itms: int


class IngestionTimeseries(BaseModel):
    daily_ingestion: list[DailyBucket]


class IngestionDashboard(BaseModel):
    generated_at: str  # ISO 8601 UTC with Z
    totals: IngestionTotals
    latest_run: IngestionLatestRun
    sources: list[IngestionSourceStatus]
    timeseries: IngestionTimeseries


# --- Ingestion log ---


class IngestionLogItem(BaseModel):
    ts: str
    level: str
    event: str
    component: str
    source: str | None = None
    source_id: str | None = None
    instance_id: str | None = None
    pipeline_run_id: str | None = None
    message: str
    details: dict = {}


class IngestionLogResponse(BaseModel):
    total: int
    items: list[IngestionLogItem]


# --- Worker status ---


class WorkerStatus(BaseModel):
    component: str
    name: str
    status: str  # "healthy" | "stale" | "stopped" | "error" | "unknown"
    last_event: str | None
    last_level: str | None
    last_message: str | None
    last_ts: str | None  # ISO Z
    age_seconds: float | None
    events_24h: int


class WorkerStatusResponse(BaseModel):
    workers: list[WorkerStatus]
    generated_at: str


# --- Firma (unified company profile) ---


class FirmaStatsBlock(BaseModel):
    contract_count: int
    total_value: float
    last_contract_at: str | None


class FirmaStats(BaseModel):
    as_supplier: FirmaStatsBlock | None
    as_procurer: FirmaStatsBlock | None


class FirmaTopContract(BaseModel):
    id: str
    title: str
    value: float | None
    year: int | None
    counterparty_name: str | None
    counterparty_ico: str | None
    role: str  # "supplier" | "procurer"


class FirmaTopCpv(BaseModel):
    code: str
    label: str
    contract_count: int
    total_value: float


class FirmaProfile(BaseModel):
    ico: str
    name: str
    roles: list[str]
    primary_role: str
    stats: FirmaStats
    top_cpvs: list[FirmaTopCpv]
    top_contracts: list[FirmaTopContract]
    spend_by_year: list[SpendByYear]


# --- Graph (Cytoscape-compatible) ---


class CytoNodeData(BaseModel):
    id: str
    label: str
    type: str  # "procurer" | "supplier"
    value: float = 0.0


class CytoEdgeData(BaseModel):
    id: str
    source: str
    target: str
    label: str = ""
    value: float = 0.0


class CytoNode(BaseModel):
    data: CytoNodeData


class CytoEdge(BaseModel):
    data: CytoEdgeData


class GraphResponse(BaseModel):
    nodes: list[CytoNode]
    edges: list[CytoEdge]

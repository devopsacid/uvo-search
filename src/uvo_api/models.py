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

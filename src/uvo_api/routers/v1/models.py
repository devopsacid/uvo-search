"""Public /v1 response models — English field names, consistent envelope."""

from pydantic import BaseModel


class Pagination(BaseModel):
    next_cursor: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Documented error model returned on any 4xx/5xx from the /v1 API."""

    error: ErrorBody


# --- Companies ---------------------------------------------------------------


class CompanyCard(BaseModel):
    ico: str
    name: str
    roles: list[str]
    contract_count: int
    total_value: float


class CompanyListResponse(BaseModel):
    data: list[CompanyCard]
    pagination: Pagination


class CompanyRecord(BaseModel):
    ico: str
    name: str
    roles: list[str]


class CompanyRecordResponse(BaseModel):
    data: CompanyRecord
    pagination: Pagination = Pagination()


class Counterparty(BaseModel):
    ico: str | None
    name: str | None
    role: str
    contract_count: int
    total_value: float


class SpendYear(BaseModel):
    year: int
    total_value: float


class CpvBreakdownRow(BaseModel):
    code: str
    label: str
    contract_count: int
    total_value: float
    share: float  # percent of the company's total value


class CompanyProfile(BaseModel):
    ico: str
    name: str
    roles: list[str]
    contract_count: int
    total_value: float
    spend_by_year: list[SpendYear]
    top_procurers: list[Counterparty]
    top_suppliers: list[Counterparty]
    cpv_breakdown: list[CpvBreakdownRow]
    cpv_concentration: float  # Herfindahl-Hirschman index over CPV value share, 0-1


class CompanyProfileResponse(BaseModel):
    data: CompanyProfile
    pagination: Pagination = Pagination()


# --- Contracts ---------------------------------------------------------------


class Contract(BaseModel):
    id: str
    title: str
    procurer_name: str
    procurer_ico: str
    supplier_name: str | None
    supplier_ico: str | None
    value: float
    cpv_code: str | None
    year: int
    status: str


class ContractListResponse(BaseModel):
    data: list[Contract]
    pagination: Pagination


class ContractDetail(Contract):
    all_suppliers: list[dict]
    publication_date: str | None


class ContractDetailResponse(BaseModel):
    data: ContractDetail
    pagination: Pagination = Pagination()

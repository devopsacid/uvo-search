"""Canonical intermediate data schema for the ETL pipeline.

All data sources (Vestník XML, CRZ, TED) normalize their
raw data to these models before writing to MongoDB or Neo4j.
"""

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field


class CanonicalAddress(BaseModel):
    street: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country_code: str = "SK"


class CanonicalOrganisation(BaseModel):
    """Shared base for procurers and suppliers."""
    ico: str | None = None
    name: str
    name_slug: str
    dic: str | None = None
    ic_dph: str | None = None
    address: CanonicalAddress | None = None
    country_code: str = "SK"
    sources: list[str] = []


class CanonicalProcurer(CanonicalOrganisation):
    organisation_type: str | None = None


class CanonicalSupplier(CanonicalOrganisation):
    pass


class CanonicalAward(BaseModel):
    supplier: CanonicalSupplier
    value: float | None = None
    currency: str = "EUR"
    contract_number: str | None = None
    signing_date: date | None = None


class CanonicalNotice(BaseModel):
    """One procurement notice/contract award, source-independent."""

    # Deduplication: (source, source_id) is the primary unique key
    source: Literal["vestnik", "crz", "ted", "uvo"]
    source_id: str

    notice_type: Literal[
        "contract_notice",
        "contract_award",
        "contract_modification",
        "cancellation",
        "prior_information",
        "other",
    ]
    status: Literal["announced", "awarded", "cancelled", "unknown"] = "unknown"

    title: str
    description: str | None = None
    procedure_type: str | None = None

    procurer: CanonicalProcurer | None = None
    awards: list[CanonicalAward] = []

    cpv_code: str | None = None
    cpv_codes_additional: list[str] = []
    nuts_code: str | None = None

    estimated_value: float | None = None
    final_value: float | None = None
    currency: str = "EUR"

    publication_date: date | None = None
    deadline_date: date | None = None
    award_date: date | None = None

    vestnik_number: str | None = None
    ted_notice_id: str | None = None
    crz_contract_id: str | None = None

    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    pipeline_run_id: str | None = None


class PipelineReport(BaseModel):
    """Summary returned by the orchestrator after a pipeline run."""
    run_id: str
    mode: str
    started_at: datetime
    finished_at: datetime | None = None
    notices_inserted: int = 0
    notices_updated: int = 0
    errors: list[str] = []
    source_counts: dict[str, int] = {}

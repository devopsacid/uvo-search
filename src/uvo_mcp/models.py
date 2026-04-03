"""Pydantic data models for procurement, subject, and pagination."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationSummary(BaseModel):
    total: int = Field(description="Total number of matching records")
    page: int = Field(description="Current page number (1-based)")
    page_size: int = Field(description="Number of records per page")
    total_pages: int = Field(description="Total number of pages")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = Field(description="List of records on this page")
    pagination: PaginationSummary = Field(description="Pagination metadata")


class SupplierSummary(BaseModel):
    id: str = Field(description="Unique identifier for the supplier")
    name: str = Field(description="Name of the supplier")
    ico: str | None = Field(default=None, description="Company registration number (IČO)")


class Procurement(BaseModel):
    id: str = Field(description="Unique identifier for the procurement")
    name: str = Field(description="Title or name of the procurement")
    value: float | None = Field(default=None, description="Contract value")
    currency: str = Field(default="EUR", description="Currency of the contract value")
    year: int | None = Field(default=None, description="Year of the procurement")
    cpv_code: str | None = Field(default=None, description="CPV code for procurement category")
    contracting_authority: str | None = Field(default=None, description="Name of the contracting authority")
    suppliers: list[SupplierSummary] = Field(default=[], description="List of awarded suppliers")


class Subject(BaseModel):
    id: str = Field(description="Unique identifier for the subject (authority or supplier)")
    name: str = Field(description="Name of the subject")
    ico: str | None = Field(default=None, description="Company registration number (IČO)")
    total_contracts: int | None = Field(default=None, description="Total number of contracts")
    total_value: float | None = Field(default=None, description="Total value of all contracts")

"""Tests for Pydantic data models: PaginationSummary, PaginatedResponse, Procurement, SupplierSummary, Subject."""

from uvo_mcp.models import (
    PaginatedResponse,
    PaginationSummary,
    Procurement,
    Subject,
    SupplierSummary,
)


class TestPaginationSummary:
    def test_create_pagination_summary(self):
        ps = PaginationSummary(total=100, page=1, page_size=10, total_pages=10)
        assert ps.total == 100
        assert ps.page == 1
        assert ps.page_size == 10
        assert ps.total_pages == 10

    def test_pagination_summary_serialization(self):
        ps = PaginationSummary(total=50, page=2, page_size=25, total_pages=2)
        data = ps.model_dump()
        assert data["total"] == 50
        assert data["page"] == 2
        assert data["page_size"] == 25
        assert data["total_pages"] == 2


class TestPaginatedResponse:
    def test_create_paginated_response_with_procurement(self):
        p = Procurement(id="proc-1", name="Test procurement")
        ps = PaginationSummary(total=1, page=1, page_size=10, total_pages=1)
        response = PaginatedResponse[Procurement](items=[p], pagination=ps)
        assert len(response.items) == 1
        assert response.items[0].id == "proc-1"
        assert response.pagination.total == 1

    def test_paginated_response_serialization(self):
        s = Subject(id="sub-1", name="Test subject")
        ps = PaginationSummary(total=1, page=1, page_size=10, total_pages=1)
        response = PaginatedResponse[Subject](items=[s], pagination=ps)
        data = response.model_dump()
        assert "items" in data
        assert "pagination" in data
        assert data["items"][0]["id"] == "sub-1"

    def test_paginated_response_empty(self):
        ps = PaginationSummary(total=0, page=1, page_size=10, total_pages=0)
        response = PaginatedResponse[Procurement](items=[], pagination=ps)
        assert response.items == []
        assert response.pagination.total == 0


class TestProcurement:
    def test_create_procurement_minimal(self):
        p = Procurement(id="proc-123", name="Road construction")
        assert p.id == "proc-123"
        assert p.name == "Road construction"
        assert p.value is None
        assert p.currency == "EUR"
        assert p.suppliers == []

    def test_create_procurement_full(self):
        supplier = SupplierSummary(id="sup-1", name="Supplier Corp")
        p = Procurement(
            id="proc-456",
            name="IT Services",
            value=50000.0,
            currency="EUR",
            year=2024,
            cpv_code="72000000",
            contracting_authority="Ministry of Finance",
            suppliers=[supplier],
        )
        assert p.value == 50000.0
        assert p.year == 2024
        assert p.cpv_code == "72000000"
        assert p.contracting_authority == "Ministry of Finance"
        assert len(p.suppliers) == 1
        assert p.suppliers[0].name == "Supplier Corp"

    def test_procurement_serialization_roundtrip(self):
        p = Procurement(id="proc-789", name="Bridge repair", value=1000000.0, year=2023)
        data = p.model_dump()
        p2 = Procurement(**data)
        assert p2.id == p.id
        assert p2.name == p.name
        assert p2.value == p.value
        assert p2.year == p.year


class TestSupplierSummary:
    def test_create_supplier_summary(self):
        s = SupplierSummary(id="sup-1", name="ACME s.r.o.")
        assert s.id == "sup-1"
        assert s.name == "ACME s.r.o."
        assert s.ico is None

    def test_supplier_summary_full(self):
        s = SupplierSummary(id="sup-2", name="Tech Corp a.s.", ico="12345678")
        assert s.ico == "12345678"


class TestSubject:
    def test_create_subject_minimal(self):
        s = Subject(id="sub-1", name="Ministry of Transport")
        assert s.id == "sub-1"
        assert s.name == "Ministry of Transport"
        assert s.ico is None
        assert s.total_contracts is None
        assert s.total_value is None

    def test_create_subject_full(self):
        s = Subject(
            id="sub-2",
            name="City of Bratislava",
            ico="87654321",
            total_contracts=150,
            total_value=5000000.0,
        )
        assert s.ico == "87654321"
        assert s.total_contracts == 150
        assert s.total_value == 5000000.0

    def test_subject_serialization(self):
        s = Subject(id="sub-3", name="Railway Authority", total_contracts=42)
        data = s.model_dump()
        assert data["id"] == "sub-3"
        assert data["name"] == "Railway Authority"
        assert data["total_contracts"] == 42
        assert data["total_value"] is None

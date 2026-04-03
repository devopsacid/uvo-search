"""Tests for procurement MCP tools."""

import httpx
import pytest

from uvo_mcp.tools.procurements import get_procurement_detail, search_completed_procurements

SAMPLE_PROCUREMENT_RESPONSE = {
    "summary": {"total": 2, "limit": 20, "offset": 0},
    "data": [
        {
            "id": "1001",
            "nazov": "IT Infrastructure",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 150000.0,
            "datum_zverejnenia": "2024-01-15",
        },
        {
            "id": "1002",
            "nazov": "Office Supplies",
            "obstaravatel": {"ico": "11223344", "nazov": "City Hall"},
            "dodavatelia": [],
            "hodnota_zmluvy": 5000.0,
            "datum_zverejnenia": "2024-01-20",
        },
    ],
}


class TestSearchCompletedProcurements:
    @pytest.mark.asyncio
    async def test_basic_search_returns_paginated_response(self, mock_context):
        ctx, mock = mock_context
        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(200, json=SAMPLE_PROCUREMENT_RESPONSE)
        )

        result = await search_completed_procurements(ctx)

        assert result["summary"]["total"] == 2
        assert len(result["data"]) == 2
        assert result["data"][0]["id"] == "1001"

    @pytest.mark.asyncio
    async def test_search_with_cpv_codes_passes_correct_params(self, mock_context):
        ctx, mock = mock_context
        route = mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(200, json=SAMPLE_PROCUREMENT_RESPONSE)
        )

        await search_completed_procurements(ctx, cpv_codes=["72000000-5"])

        assert route.called
        request = route.calls[0].request
        assert "72000000-5" in request.url.query.decode()

    @pytest.mark.asyncio
    async def test_search_with_date_range_passes_correct_params(self, mock_context):
        ctx, mock = mock_context
        route = mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(200, json=SAMPLE_PROCUREMENT_RESPONSE)
        )

        await search_completed_procurements(ctx, date_from="2024-01-01", date_to="2024-12-31")

        assert route.called
        request = route.calls[0].request
        query = request.url.query.decode()
        assert "datum_zverejnenia_od" in query
        assert "datum_zverejnenia_do" in query
        assert "2024-01-01" in query
        assert "2024-12-31" in query

    @pytest.mark.asyncio
    async def test_search_with_text_query(self, mock_context):
        ctx, mock = mock_context
        route = mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(200, json=SAMPLE_PROCUREMENT_RESPONSE)
        )

        await search_completed_procurements(ctx, text_query="software")

        assert route.called
        request = route.calls[0].request
        assert "text=software" in request.url.query.decode()

    @pytest.mark.asyncio
    async def test_api_error_returns_structured_error_dict(self, mock_context):
        ctx, mock = mock_context
        mock.get("/api/ukoncene_obstaravania").mock(return_value=httpx.Response(500))

        result = await search_completed_procurements(ctx)

        assert "error" in result
        assert result["status_code"] == 500

    @pytest.mark.asyncio
    async def test_network_error_returns_structured_error_dict(self, mock_context):
        ctx, mock = mock_context
        mock.get("/api/ukoncene_obstaravania").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await search_completed_procurements(ctx)

        assert "error" in result


class TestGetProcurementDetail:
    @pytest.mark.asyncio
    async def test_returns_procurement_with_suppliers(self, mock_context):
        ctx, mock = mock_context
        detail_response = {
            "summary": {"total": 1, "limit": 20, "offset": 0},
            "data": [
                {
                    "id": "1001",
                    "nazov": "IT Infrastructure",
                    "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
                    "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
                    "hodnota_zmluvy": 150000.0,
                }
            ],
        }
        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(200, json=detail_response)
        )

        result = await get_procurement_detail(ctx, "1001")

        assert result["id"] == "1001"
        assert len(result["dodavatelia"]) == 1
        assert result["dodavatelia"][0]["ico"] == "87654321"

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self, mock_context):
        ctx, mock = mock_context
        empty_response = {"summary": {"total": 0, "limit": 20, "offset": 0}, "data": []}
        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(200, json=empty_response)
        )

        result = await get_procurement_detail(ctx, "9999")

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_api_error_returns_error_dict(self, mock_context):
        ctx, mock = mock_context
        mock.get("/api/ukoncene_obstaravania").mock(return_value=httpx.Response(500))

        result = await get_procurement_detail(ctx, "1001")

        assert "error" in result
        assert result["status_code"] == 500

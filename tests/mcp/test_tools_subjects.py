"""Tests for subject (procurer and supplier) MCP tools."""

import httpx
import pytest

from uvo_mcp.tools.subjects import find_procurer, find_supplier

SAMPLE_SUBJECT_RESPONSE = {
    "summary": {"total": 2, "limit": 20, "offset": 0},
    "data": [
        {
            "id": "101",
            "nazov": "Ministry of Finance",
            "ico": "00151742",
            "pocet_zakaziek": 45,
            "celkova_hodnota": 1200000.0,
        },
        {
            "id": "102",
            "nazov": "Ministry of Interior",
            "ico": "00151866",
            "pocet_zakaziek": 30,
            "celkova_hodnota": 800000.0,
        },
    ],
}

SAMPLE_SUPPLIER_RESPONSE = {
    "summary": {"total": 2, "limit": 20, "offset": 0},
    "data": [
        {
            "id": "201",
            "nazov": "Tech Corp s.r.o.",
            "ico": "87654321",
            "pocet_zakaziek": 12,
            "celkova_hodnota": 350000.0,
        },
        {
            "id": "202",
            "nazov": "Software Solutions a.s.",
            "ico": "11223344",
            "pocet_zakaziek": 8,
            "celkova_hodnota": 200000.0,
        },
    ],
}


class TestFindProcurer:
    @pytest.mark.asyncio
    async def test_search_by_name_returns_results(self, mock_context):
        ctx, mock = mock_context
        route = mock.get("/api/obstaravatelia").mock(
            return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
        )

        result = await find_procurer(ctx, name_query="Ministry")

        assert route.called
        request = route.calls[0].request
        assert "text=Ministry" in request.url.query.decode()
        assert result["summary"]["total"] == 2
        assert len(result["data"]) == 2

    @pytest.mark.asyncio
    async def test_search_by_ico_exact_match(self, mock_context):
        ctx, mock = mock_context
        route = mock.get("/api/obstaravatelia").mock(
            return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
        )

        await find_procurer(ctx, ico="00151742")

        assert route.called
        request = route.calls[0].request
        assert "ico=00151742" in request.url.query.decode()

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_context):
        ctx, mock = mock_context
        empty_response = {"summary": {"total": 0, "limit": 20, "offset": 0}, "data": []}
        mock.get("/api/obstaravatelia").mock(return_value=httpx.Response(200, json=empty_response))

        result = await find_procurer(ctx, name_query="nonexistent")

        assert result["summary"]["total"] == 0
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_api_error_returns_error_dict(self, mock_context):
        ctx, mock = mock_context
        mock.get("/api/obstaravatelia").mock(return_value=httpx.Response(500))

        result = await find_procurer(ctx)

        assert "error" in result
        assert result["status_code"] == 500


class TestFindSupplier:
    @pytest.mark.asyncio
    async def test_search_by_name_returns_results(self, mock_context):
        ctx, mock = mock_context
        route = mock.get("/api/dodavatelia").mock(
            return_value=httpx.Response(200, json=SAMPLE_SUPPLIER_RESPONSE)
        )

        result = await find_supplier(ctx, name_query="Tech")

        assert route.called
        request = route.calls[0].request
        assert "text=Tech" in request.url.query.decode()
        assert result["summary"]["total"] == 2
        assert len(result["data"]) == 2

    @pytest.mark.asyncio
    async def test_search_by_ico(self, mock_context):
        ctx, mock = mock_context
        route = mock.get("/api/dodavatelia").mock(
            return_value=httpx.Response(200, json=SAMPLE_SUPPLIER_RESPONSE)
        )

        await find_supplier(ctx, ico="87654321")

        assert route.called
        request = route.calls[0].request
        assert "ico=87654321" in request.url.query.decode()

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_context):
        ctx, mock = mock_context
        empty_response = {"summary": {"total": 0, "limit": 20, "offset": 0}, "data": []}
        mock.get("/api/dodavatelia").mock(return_value=httpx.Response(200, json=empty_response))

        result = await find_supplier(ctx, name_query="nonexistent")

        assert result["summary"]["total"] == 0
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_api_error_returns_error_dict(self, mock_context):
        ctx, mock = mock_context
        mock.get("/api/dodavatelia").mock(return_value=httpx.Response(503))

        result = await find_supplier(ctx)

        assert "error" in result
        assert result["status_code"] == 503

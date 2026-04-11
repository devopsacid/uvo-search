"""Tests for Neo4j loader (unit level — mocked session)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_pipeline.loaders.neo4j import merge_notice_node, merge_procurer_node, merge_supplier_node
from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer, CanonicalSupplier
from datetime import date


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.run = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_merge_procurer_with_ico(mock_session):
    procurer = CanonicalProcurer(ico="12345678", name="Test Procurer", name_slug="test-procurer")
    await merge_procurer_node(mock_session, procurer)
    mock_session.run.assert_called_once()
    call_args = mock_session.run.call_args
    assert "MERGE (p:Procurer {ico: $ico})" in call_args[0][0]


@pytest.mark.asyncio
async def test_merge_procurer_without_ico_uses_name_slug(mock_session):
    procurer = CanonicalProcurer(name="No ICO Org", name_slug="no-ico-org")
    await merge_procurer_node(mock_session, procurer)
    mock_session.run.assert_called_once()
    assert "name_slug" in mock_session.run.call_args[0][0]


@pytest.mark.asyncio
async def test_merge_supplier_with_ico(mock_session):
    supplier = CanonicalSupplier(ico="87654321", name="Test Supplier", name_slug="test-supplier")
    await merge_supplier_node(mock_session, supplier)
    mock_session.run.assert_called_once()
    assert "MERGE (s:Supplier {ico: $ico})" in mock_session.run.call_args[0][0]


@pytest.mark.asyncio
async def test_merge_notice_node(mock_session):
    notice = CanonicalNotice(
        source="vestnik",
        source_id="test-123",
        notice_type="contract_award",
        title="Test Notice",
        publication_date=date(2024, 1, 15),
    )
    await merge_notice_node(mock_session, notice)
    mock_session.run.assert_called_once()
    assert "MERGE (n:Notice" in mock_session.run.call_args[0][0]

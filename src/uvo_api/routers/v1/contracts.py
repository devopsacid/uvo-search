"""Public /v1 contract endpoints — search and detail."""

from fastapi import APIRouter, Query

from uvo_api._schema import map_contract_detail, map_contract_row
from uvo_api.db import get_notice_repo
from uvo_api.routers.v1._common import decode_cursor, next_pagination
from uvo_api.routers.v1.models import (
    Contract,
    ContractDetail,
    ContractDetailResponse,
    ContractListResponse,
    Pagination,
)
from uvo_api.v1_errors import ApiV1Error

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("", response_model=ContractListResponse)
async def search_contracts(
    q: str | None = Query(None, description="Full-text query over title/description/parties."),
    cpv: str | None = Query(None, description="CPV code filter."),
    date_from: str | None = Query(None, description="ISO date lower bound (publication_date)."),
    date_to: str | None = Query(None, description="ISO date upper bound (publication_date)."),
    min_value: float | None = Query(None, description="Minimum final contract value."),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> ContractListResponse:
    """Search completed procurement contracts."""
    offset = decode_cursor(cursor)
    result = await get_notice_repo().search(
        text_query=q or None,
        cpv_codes=[cpv] if cpv else None,
        date_from=date_from,
        date_to=date_to,
        value_min=min_value,
        limit=limit,
        offset=offset,
    )
    items = result.get("items", [])
    total = result.get("total", len(items))

    rows = [Contract(**map_contract_row(i).model_dump()) for i in items]

    return ContractListResponse(
        data=rows,
        pagination=next_pagination(offset, limit, len(items), total),
    )


@router.get("/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(contract_id: str) -> ContractDetailResponse:
    """Full detail for a single contract by id."""
    result = await get_notice_repo().get_by_source_id(contract_id)
    if "error" in result:
        raise ApiV1Error(404, "contract_not_found", f"No contract found for id {contract_id}.")

    detail = map_contract_detail(result)
    return ContractDetailResponse(
        data=ContractDetail(**detail.model_dump()),
        pagination=Pagination(),
    )

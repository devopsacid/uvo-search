"""Mapping helpers between MCP English schema and API response models.

MCP tools return:
- list data under `items` (not `data`)
- contracts with fields: `_id`, `title`, `procurer.{ico,name}`, `final_value`,
  `estimated_value`, `cpv_code`, `publication_date`, `award_date`, `awards[]`, `status`
- entities with fields: `ico`, `name`, `contract_count`, `total_value`
"""

from datetime import datetime, timezone

from uvo_api.models import ContractDetail, ContractRow

_MIN_YEAR = 1993
_MAX_YEAR_DELTA = 5  # mirror uvo_pipeline.utils.date_validation


def year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            year = int(date_str[:4])
        except ValueError:
            return 0
        max_year = datetime.now(timezone.utc).year + _MAX_YEAR_DELTA
        if _MIN_YEAR <= year <= max_year:
            return year
    return 0


def status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def contract_value(item: dict) -> float:
    for key in ("final_value", "estimated_value"):
        v = item.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def contract_date(item: dict) -> str | None:
    return item.get("award_date") or item.get("publication_date")


def first_supplier(item: dict) -> dict:
    awards = item.get("awards") or []
    return awards[0] if awards else {}


def map_contract_row(item: dict) -> ContractRow:
    year = year_from_date(contract_date(item))
    award = first_supplier(item)
    procurer = item.get("procurer") or {}
    status = item.get("status") or status_from_year(year)
    return ContractRow(
        id=str(item.get("_id") or item.get("id") or ""),
        title=item.get("title") or "",
        procurer_name=procurer.get("name") or "",
        procurer_ico=procurer.get("ico") or "",
        supplier_name=award.get("supplier_name") or award.get("name"),
        supplier_ico=award.get("supplier_ico") or award.get("ico"),
        value=contract_value(item),
        cpv_code=item.get("cpv_code"),
        year=year,
        status=status,
    )


def map_contract_detail(item: dict) -> ContractDetail:
    row = map_contract_row(item)
    return ContractDetail(
        **row.model_dump(),
        all_suppliers=item.get("awards") or [],
        publication_date=item.get("publication_date"),
    )

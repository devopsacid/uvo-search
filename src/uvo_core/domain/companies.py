"""Company merge-by-ICO and role resolution — pure domain functions.

Shared by the /api firma + search routers and the /v1 companies router, all of
which combine supplier and procurer entity results into a single per-company
view keyed by ICO. Inputs and outputs are plain dicts so callers keep ownership
of their response models.
"""

from __future__ import annotations


def merge_companies_by_ico(
    suppliers: list[dict],
    procurers: list[dict],
    *,
    vector: list[dict] | None = None,
    accumulate: bool = False,
    skip_empty_ico: bool = False,
    sort_by_count: bool = False,
) -> list[dict]:
    """Merge supplier/procurer (and optional vector) entity rows into one row per ICO.

    Each output row is ``{ico, name, roles, contract_count, total_value}``.

    - ``vector`` rows are seeded first (roles taken from the row, counts zeroed);
      rows with an empty ICO are always skipped.
    - ``accumulate`` sums contract_count/total_value when an ICO recurs (list
      views); otherwise a recurring ICO only gains the extra role (search views).
    - ``skip_empty_ico`` drops supplier/procurer rows without an ICO.
    - ``sort_by_count`` returns rows sorted by contract_count desc (stable).
    """
    merged: dict[str, dict] = {}

    for item in vector or []:
        ico = str(item.get("ico") or "")
        if not ico:
            continue
        merged[ico] = {
            "ico": ico,
            "name": item.get("name") or "",
            "roles": list(item.get("roles") or []),
            "contract_count": 0,
            "total_value": 0.0,
        }

    def _add(item: dict, role: str) -> None:
        ico = str(item.get("ico") or "")
        if skip_empty_ico and not ico:
            return
        existing = merged.get(ico)
        if existing is None:
            merged[ico] = {
                "ico": ico,
                "name": item.get("name") or "",
                "roles": [role],
                "contract_count": int(item.get("contract_count") or 0),
                "total_value": float(item.get("total_value") or 0.0),
            }
            return
        if role not in existing["roles"]:
            existing["roles"].append(role)
        if accumulate:
            existing["contract_count"] += int(item.get("contract_count") or 0)
            existing["total_value"] += float(item.get("total_value") or 0.0)

    for item in suppliers:
        _add(item, "supplier")
    for item in procurers:
        _add(item, "procurer")

    rows = list(merged.values())
    if sort_by_count:
        rows.sort(key=lambda r: r["contract_count"], reverse=True)
    return rows


def primary_role(
    *,
    is_supplier: bool,
    is_procurer: bool,
    supplier_count: int,
    procurer_count: int,
) -> str:
    """Pick the dominant role for a company that may act in both roles.

    A pure procurer stays ``procurer``; otherwise ``supplier`` wins, including
    on a count tie.
    """
    if not is_supplier:
        return "procurer"
    if not is_procurer or supplier_count >= procurer_count:
        return "supplier"
    return "procurer"

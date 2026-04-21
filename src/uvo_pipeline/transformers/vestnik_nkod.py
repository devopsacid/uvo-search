"""Vestník NKOD transformer — map eForms bulletin items to CanonicalNotice."""

import logging
import re
from datetime import date

from slugify import slugify

from uvo_pipeline.models import CanonicalAddress, CanonicalAward, CanonicalNotice, CanonicalProcurer, CanonicalSupplier

logger = logging.getLogger(__name__)

NOTICE_TYPE_MAP = {
    "result": "contract_award",
    "planning": "contract_notice",
    "change": "contract_modification",
}

STATUS_MAP = {
    "contract_award": "awarded",
    "contract_notice": "announced",
    "contract_modification": "unknown",
}

_ID_RE = re.compile(r"\(ID:\s*([^)]+)\)\s*$")
# eForms panel labels embed entity IDs in parens at the end, e.g. "(ORG-0001)", "(TEN-0002)".
# This regex extracts that ID from the Slovak label text.
_PANEL_ID_RE = re.compile(r"\(([A-Z]+-\d+)\)\s*$")
_ICO_RE = re.compile(r"^\d{8}$")


def _flatten_eforms(components: list[dict]) -> dict[str, str]:
    flat: dict[str, str] = {}
    if not isinstance(components, list):
        return flat
    for component in components:
        if not isinstance(component, dict):
            continue
        try:
            key = component.get("key")
            value = component.get("value")
            if key is not None and value is not None:
                flat.setdefault(key, value)
            sub = component.get("components")
            if sub:
                for k, v in _flatten_eforms(sub).items():
                    flat.setdefault(k, v)
        except Exception:
            continue
    return flat


def _lookup(flat: dict[str, str], *codes: str) -> str | None:
    for code in codes:
        v = flat.get(code)
        if v:
            return v
    return None


def _parse_partner(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    m = _ID_RE.search(value)
    if m:
        name = value[: m.start()].strip()
        partner_id = m.group(1).strip()
        return name or None, partner_id
    return value.strip() or None, None


def _parse_order(value: str | None) -> str | None:
    if not value:
        return None
    m = _ID_RE.search(value)
    if m:
        return value[: m.start()].strip() or None
    return value.strip() or None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        logger.warning("vestnik_nkod: bad date: %r", value)
        return None


def _parse_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    # Slovak-formatted values use non-breaking spaces as thousand separators.
    cleaned = str(value).replace("\xa0", "").replace(" ", "")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _panel_id(panel: dict) -> str | None:
    """Extract entity ID (e.g. ORG-0001) from a panel's Slovak label text."""
    lang_text = panel.get("lang", {}).get("sk", {})
    for text in lang_text.values():
        m = _PANEL_ID_RE.search(str(text))
        if m:
            return m.group(1)
    return None


def _collect_panels(components: list[dict], panel_key: str) -> list[dict]:
    """Return all direct children of the group with key=panel_key's parent that match *_panel."""
    # Walk the tree to find the group, then return its panel children.
    for c in (components or []):
        if not isinstance(c, dict):
            continue
        if c.get("key") == panel_key:
            return [p for p in c.get("components", []) if isinstance(p, dict) and p.get("key", "").endswith("_panel")]
        found = _collect_panels(c.get("components", []), panel_key)
        if found is not None and found != []:
            return found
    return []


def _build_org_map(components: list[dict]) -> dict[str, dict]:
    """Build ORG-id -> org-info dict from GR-Organisations panels."""
    org_map: dict[str, dict] = {}
    panels = _collect_panels(components, "GR-Organisations")
    for panel in panels:
        org_id = _panel_id(panel)
        if not org_id:
            continue
        flat = _flatten_eforms(panel.get("components", []))
        name = flat.get("BT-500-Organization-Company")
        if not name:
            continue
        cin = flat.get("BT-501-Organization-Company-CIN")
        ico = cin if (cin and _ICO_RE.fullmatch(cin)) else None
        org_map[org_id] = {
            "name": name,
            "ico": ico,
            "address": CanonicalAddress(
                street=" ".join(filter(None, [
                    flat.get("BT-510(a)-Organization-Company"),
                    flat.get("BT-510(b)-Organization-Company"),
                ])) or None,
                city=flat.get("BT-513-Organization-Company"),
                postal_code=flat.get("BT-512-Organization-Company"),
                country_code=flat.get("BT-514-Organization-Company", "SK"),
            ),
        }
    return org_map


def _build_tp_map(components: list[dict]) -> dict[str, str]:
    """Build TPA-id -> ORG-id dict from GR-TenderingParty panels."""
    tp_map: dict[str, str] = {}
    panels = _collect_panels(components, "GR-TenderingParty")
    for panel in panels:
        tp_id = _panel_id(panel)
        if not tp_id:
            continue
        flat = _flatten_eforms(panel.get("components", []))
        org_id = flat.get("OPT-300-Tenderer")
        if org_id:
            tp_map[tp_id] = org_id
    return tp_map


def _build_tender_map(components: list[dict]) -> dict[str, dict]:
    """Build TEN-id -> {value, currency, tp_id} dict from GR-LotTender panels."""
    ten_map: dict[str, dict] = {}
    panels = _collect_panels(components, "GR-LotTender")
    for panel in panels:
        ten_id = _panel_id(panel)
        if not ten_id:
            continue
        flat = _flatten_eforms(panel.get("components", []))
        # OPT-310-Tender holds the TPA-XXXX identifier. BT-3201-Tender is a
        # user-facing Slovak label ("Ponuka č. 1") in many bulletins, so
        # linking through it fails for ~99% of real data.
        ten_map[ten_id] = {
            "value": _parse_float(flat.get("BT-720-Tender_value")),
            "currency": flat.get("BT-720-Tender_currency", "EUR"),
            "tp_id": flat.get("OPT-310-Tender") or flat.get("BT-3201-Tender"),
        }
    return ten_map


def _build_awards(components: list[dict]) -> list[CanonicalAward]:
    """Walk eForms tree to extract awards from LotResults with BT-142=selec-w."""
    org_map = _build_org_map(components)
    tp_map = _build_tp_map(components)
    ten_map = _build_tender_map(components)

    awards: list[CanonicalAward] = []
    panels = _collect_panels(components, "GR-LotResult")
    for panel in panels:
        flat = _flatten_eforms(panel.get("components", []))
        if flat.get("BT-142-LotResult") != "selec-w":
            continue
        opt_320 = flat.get("OPT-320-LotResult")
        if not opt_320:
            continue
        # OPT-320-LotResult may be stored as a string list repr "['TEN-0001']"
        # or as a plain string "TEN-0001".
        if isinstance(opt_320, str) and opt_320.startswith("["):
            ten_ids = re.findall(r"TEN-\d+", opt_320)
        elif isinstance(opt_320, list):
            ten_ids = [str(x) for x in opt_320]
        else:
            ten_ids = [opt_320]

        # Fallback lot-result value (BT-710) when tender value is absent.
        lot_value = _parse_float(flat.get("BT-710-LotResult_value"))
        lot_currency = flat.get("BT-710-LotResult_currency", "EUR")

        for ten_id in ten_ids:
            ten = ten_map.get(ten_id)
            if not ten:
                continue
            tp_id = ten.get("tp_id")
            org_id = tp_map.get(tp_id) if tp_id else None
            org = org_map.get(org_id) if org_id else None
            if not org:
                continue
            value = ten.get("value") if ten.get("value") is not None else lot_value
            currency = ten.get("currency") or lot_currency
            awards.append(CanonicalAward(
                supplier=CanonicalSupplier(
                    name=org["name"],
                    name_slug=slugify(org["name"]),
                    ico=org.get("ico"),
                    address=org.get("address"),
                    sources=["vestnik", "uvo"],
                ),
                value=value,
                currency=currency,
            ))
    return awards


def transform_notice(raw: dict) -> CanonicalNotice:
    components = raw.get("components", [])
    metadata = next(
        (c for c in components if c.get("key") == "metadataWrapper"), {}
    ).get("components", [])
    tabs = next(
        (c for c in components if c.get("key") == "tabs"), {}
    ).get("components", [])

    flat = {**_flatten_eforms(tabs), **_flatten_eforms(metadata)}

    source_id = str(raw["id"])
    ted_notice_id = _lookup(flat, "BT-04-notice")
    notice_type = NOTICE_TYPE_MAP.get(_lookup(flat, "BT-03-notice"), "other")
    status = STATUS_MAP.get(notice_type, "unknown")

    order_name = _parse_order(_lookup(flat, "DL-Metadata-Order"))
    title = order_name or raw.get("name") or "Untitled notice"

    partner_name, _partner_id = _parse_partner(_lookup(flat, "DL-Metadata-Partner"))
    procurer = None
    if partner_name:
        # Vestník is UVO's official gazette; mark procurer provenance as both
        # so cross-source dedup links vestnik notices to any legacy UVO data.
        procurer = CanonicalProcurer(
            name=partner_name,
            name_slug=slugify(partner_name),
            ico=None,
            organisation_type=None,
            sources=["vestnik", "uvo"],
        )

    publication_date = _parse_date(raw.get("_bulletin_publish_date"))

    year = raw.get("_bulletin_year")
    number = raw.get("_bulletin_number")
    vestnik_number = f"{number}/{year}" if year is not None and number is not None else None

    cpv_code = _lookup(flat, "BT-262-Lot")
    final_value = _parse_float(_lookup(flat, "BT-720-Tender"))
    estimated_value = _parse_float(_lookup(flat, "BT-27-Lot", "BT-27-Procedure"))
    currency = _lookup(flat, "BT-720-Tender-Currency", "BT-27-Lot-Currency") or "EUR"

    all_components = raw.get("components", [])
    awards = _build_awards(all_components)

    return CanonicalNotice(
        source="vestnik",
        source_id=source_id,
        notice_type=notice_type,
        status=status,
        title=title,
        procurer=procurer,
        cpv_code=cpv_code,
        estimated_value=estimated_value,
        final_value=final_value,
        currency=currency,
        publication_date=publication_date,
        vestnik_number=vestnik_number,
        ted_notice_id=ted_notice_id,
        awards=awards,
    )

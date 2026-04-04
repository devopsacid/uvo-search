"""Vestník XML extractor — parses UBL/eForms notices from Vestník ZIP packages."""

import logging
from pathlib import Path
from typing import Iterator

from lxml import etree

logger = logging.getLogger(__name__)

# Common eForms/UBL namespaces
NAMESPACES = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}


def parse_xml_file(xml_path: Path) -> Iterator[dict]:
    """Parse one Vestník XML file. Yield one raw dict per notice.

    Handles various UBL/eForms document types.
    Each yielded dict has at minimum: notice_id, form_type, raw_xml (str).
    Additional fields extracted when available.
    """
    try:
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        logger.warning("XML parse error in %s: %s", xml_path.name, e)
        return

    # Detect document type from root tag
    root_tag = etree.QName(root.tag).localname

    # Extract notice ID
    notice_id = _xpath_text(root, "//cbc:ID[1]")
    if not notice_id:
        notice_id = xml_path.stem  # fallback to filename

    # Extract notice type code
    form_type = _xpath_text(root, "//cbc:NoticeTypeCode")

    # Extract contracting party (procurer)
    procurer_name = _xpath_text(root, "//cac:ContractingParty//cbc:Name[1]")
    procurer_id_node = _xpath_text(root, "//cac:ContractingParty//cbc:CompanyID[1]")

    # Extract values
    estimated_value = _xpath_text(root, "//cbc:EstimatedOverallContractAmount")
    total_value = _xpath_text(root, "//cbc:TotalAmount[1]") or _xpath_text(root, "//cbc:PayableAmount[1]")
    currency = root.xpath("//cbc:EstimatedOverallContractAmount/@currencyID", namespaces=NAMESPACES)

    # Extract CPV
    cpv_code = _xpath_text(root, "//cbc:ItemClassificationCode[@listName='CPV'][1]")

    # Extract dates
    publication_date = _xpath_text(root, "//cbc:IssueDate[1]") or _xpath_text(
        root, "//cbc:PublicationDate[1]"
    )

    # Extract title/description
    title = _xpath_text(root, "//cbc:Name[1]") or _xpath_text(root, "//cbc:Description[1]")

    yield {
        "notice_id": notice_id,
        "form_type": form_type,
        "root_tag": root_tag,
        "procurer_name": procurer_name,
        "procurer_ico": procurer_id_node,
        "estimated_value": estimated_value,
        "total_value": total_value,
        "currency": currency[0] if currency else "EUR",
        "cpv_code": cpv_code,
        "publication_date": publication_date,
        "title": title,
        "xml_path": str(xml_path),
    }


def _xpath_text(element, xpath: str) -> str | None:
    """Return text of first matched element, or None."""
    results = element.xpath(xpath, namespaces=NAMESPACES)
    if results and hasattr(results[0], "text"):
        return results[0].text
    if results and isinstance(results[0], str):
        return results[0]
    return None

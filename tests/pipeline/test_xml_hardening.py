"""XXE and path-traversal hardening for the Vestnik ingestion path."""

from uvo_pipeline.extractors.vestnik_xml import _make_parser
from uvo_pipeline.utils.zip_handler import cache_path_for_url

XXE_DOC = """<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>
<root><title>&xxe;</title></root>
"""


def test_external_entities_are_not_resolved(tmp_path):
    from lxml import etree

    doc = tmp_path / "xxe.xml"
    doc.write_text(XXE_DOC, encoding="utf-8")
    tree = etree.parse(str(doc), _make_parser())
    title = tree.find("title").text or ""
    assert "/etc/hostname" not in title
    assert title.strip() == "", "external entity content must not be substituted"


def test_cache_path_ignores_remote_filename(tmp_path):
    evil = "https://example.org/a/../../../../app/src/uvo_pipeline/config.py"
    dest = cache_path_for_url(evil, tmp_path)
    assert dest.parent == tmp_path
    assert dest.suffix == ".zip"


def test_cache_path_is_stable_for_same_url(tmp_path):
    url = "https://example.org/dataset.zip"
    assert cache_path_for_url(url, tmp_path) == cache_path_for_url(url, tmp_path)


def test_cache_path_differs_for_different_urls(tmp_path):
    a = cache_path_for_url("https://example.org/a.zip", tmp_path)
    b = cache_path_for_url("https://example.org/b.zip", tmp_path)
    assert a != b

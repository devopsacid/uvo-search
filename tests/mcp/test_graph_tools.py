from uvo_mcp.tools.graph import _build_cpv_graph, _build_ego_graph


def test_build_ego_graph_shape():
    start = {"ico": "111", "name": "Fakulta A", "type": "procurer", "contract_count": 5}
    related_rows = [
        {"name": "Firma B", "ico": "222", "type": "Supplier", "hops": 1,
         "contract_count": 3, "total_value": 50000},
        {"name": "Inštitúcia C", "ico": "333", "type": "Procurer", "hops": 2,
         "contract_count": 1, "total_value": 12000},
    ]
    graph = _build_ego_graph(start, related_rows)

    ids = {n["id"] for n in graph["nodes"]}
    assert ids == {"111", "222", "333"}
    start_node = next(n for n in graph["nodes"] if n["id"] == "111")
    assert start_node["type"] == "procurer"
    assert start_node["value"] == 5
    assert {e["from"] for e in graph["edges"]} == {"111"}


def test_build_cpv_graph_shape():
    rows = [
        {"procurer_ico": "111", "procurer_name": "F A",
         "supplier_ico": "222", "supplier_name": "S B",
         "contract_count": 2, "total_value": 10000},
    ]
    graph = _build_cpv_graph(rows)
    assert {n["id"] for n in graph["nodes"]} == {"111", "222"}
    edge = graph["edges"][0]
    assert edge["from"] == "111"
    assert edge["to"] == "222"
    assert edge["value"] == 10000

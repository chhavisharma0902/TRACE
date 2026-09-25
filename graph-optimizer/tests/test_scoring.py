import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import networkx as nx
from scoring import score_neighbors, top_k_recommendations


def make_test_graph():
    G = nx.MultiDiGraph()
    G.add_edge("a.py::foo", "b.py::bar", edge_type="call")
    G.add_edge("a.py::foo", "c.py::baz", edge_type="cochange", count=8)
    G.add_edge("a.py::foo", "d.py::qux", edge_type="cochange", count=2)
    return G


def test_call_only_weight():
    G = make_test_graph()
    scores = score_neighbors(G, "a.py::foo", call_weight=1.0, cochange_weight=0.0)

    assert scores["b.py::bar"] == 1.0
    assert scores.get("c.py::baz", 0) == 0.0
    assert scores.get("d.py::qux", 0) == 0.0


def test_cochange_only_weight_is_normalized():
    G = make_test_graph()
    scores = score_neighbors(G, "a.py::foo", call_weight=0.0, cochange_weight=1.0)

    # max co-change count in this graph is 8, so:
    # c.py::baz (count=8) should score 1.0 (fully normalized)
    # d.py::qux (count=2) should score 0.25
    assert scores["c.py::baz"] == 1.0
    assert scores["d.py::qux"] == 0.25
    assert scores.get("b.py::bar", 0) == 0.0


def test_combined_weights():
    G = make_test_graph()
    scores = score_neighbors(G, "a.py::foo", call_weight=0.5, cochange_weight=0.5)

    assert scores["b.py::bar"] == 0.5
    assert scores["c.py::baz"] == 0.5  # 0.5 * 1.0 (normalized)


def test_top_k_ranking():
    G = make_test_graph()
    ranked = top_k_recommendations(G, "a.py::foo", call_weight=0.5, cochange_weight=0.5, k=2)

    assert len(ranked) == 2
    # c.py::baz (strong cochange) should outrank d.py::qux (weak cochange)
    ids = [func_id for func_id, _ in ranked]
    assert "c.py::baz" in ids
    assert "d.py::qux" not in ids  # only top 2 kept, weakest dropped


def test_unknown_source_function_returns_empty():
    G = make_test_graph()
    scores = score_neighbors(G, "does_not_exist.py::nope", call_weight=1.0, cochange_weight=1.0)
    assert scores == {}


def test_isolated_node_returns_empty():
    G = nx.MultiDiGraph()
    G.add_node("lonely.py::alone")
    scores = score_neighbors(G, "lonely.py::alone", call_weight=1.0, cochange_weight=1.0)
    assert scores == {}

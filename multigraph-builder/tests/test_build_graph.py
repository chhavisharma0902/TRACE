import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from build_graph import build_unified_graph, save_graph, load_graph


def test_call_edges_added():
    ast_data = {
        "a.py::foo": ["b.py::bar"],
        "b.py::bar": [],
    }
    cochange_data = {}

    G = build_unified_graph(ast_data, cochange_data)

    assert G.has_edge("a.py::foo", "b.py::bar")
    edge_data = G.get_edge_data("a.py::foo", "b.py::bar")
    # get_edge_data on a MultiDiGraph returns a dict keyed by edge index
    assert any(e["edge_type"] == "call" for e in edge_data.values())


def test_cochange_edges_added_with_count():
    ast_data = {}
    cochange_data = {
        "a.py::foo": {"b.py::bar": 5},
        "b.py::bar": {"a.py::foo": 5},
    }

    G = build_unified_graph(ast_data, cochange_data)

    edge_data = G.get_edge_data("a.py::foo", "b.py::bar")
    assert any(
        e["edge_type"] == "cochange" and e["count"] == 5
        for e in edge_data.values()
    )


def test_parallel_edges_both_types_preserved():
    """
    The core reason we use MultiDiGraph: the same pair of nodes can have
    BOTH a call edge and a cochange edge simultaneously, and both must
    be retrievable — not overwritten.
    """
    ast_data = {"a.py::foo": ["b.py::bar"]}
    cochange_data = {"a.py::foo": {"b.py::bar": 3}}

    G = build_unified_graph(ast_data, cochange_data)

    edge_data = G.get_edge_data("a.py::foo", "b.py::bar")
    edge_types = {e["edge_type"] for e in edge_data.values()}

    assert edge_types == {"call", "cochange"}
    assert len(edge_data) == 2  # two distinct parallel edges, not one merged edge


def test_isolated_node_no_relationships():
    """
    A function with no calls and no co-change history should still
    appear as a node with zero edges, not cause an error.
    """
    ast_data = {"a.py::lonely_func": []}
    cochange_data = {}

    G = build_unified_graph(ast_data, cochange_data)

    assert "a.py::lonely_func" in G.nodes
    assert G.out_degree("a.py::lonely_func") == 0


def test_save_and_load_roundtrip(tmp_path):
    ast_data = {"a.py::foo": ["b.py::bar"]}
    cochange_data = {"a.py::foo": {"b.py::bar": 2}}

    G = build_unified_graph(ast_data, cochange_data)

    output_file = tmp_path / "unified_graph.json"
    save_graph(G, output_file)

    G_loaded = load_graph(output_file)

    assert G_loaded.number_of_nodes() == G.number_of_nodes()
    assert G_loaded.number_of_edges() == G.number_of_edges()
    assert G_loaded.has_edge("a.py::foo", "b.py::bar")

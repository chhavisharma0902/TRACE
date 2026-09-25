import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import networkx as nx
from optimize import hit_rate_at_k, run_optimization


def make_test_graph():
    G = nx.MultiDiGraph()
    # a.py::foo calls b.py::bar AND co-changed with it 10 times —
    # both signals agree, so b.py::bar should be an easy top recommendation
    G.add_edge("a.py::foo", "b.py::bar", edge_type="call")
    G.add_edge("a.py::foo", "b.py::bar", edge_type="cochange", count=10)

    # noise: a few weakly-related functions that shouldn't be recommended
    G.add_edge("a.py::foo", "c.py::noise1", edge_type="cochange", count=1)
    G.add_edge("a.py::foo", "d.py::noise2", edge_type="cochange", count=1)
    return G


def test_hit_rate_perfect_case():
    G = make_test_graph()
    ground_truth = [
        {"changed_function": "a.py::foo", "affected_function": "b.py::bar", "date": "2024-06-01"},
    ]

    rate = hit_rate_at_k(G, ground_truth, call_weight=0.5, cochange_weight=0.5, k=5)
    assert rate == 1.0  # b.py::bar should easily be in top 5 of only 3 candidates


def test_hit_rate_missing_source_function_is_skipped_not_penalized():
    G = make_test_graph()
    ground_truth = [
        {"changed_function": "nonexistent.py::ghost", "affected_function": "b.py::bar", "date": "2024-06-01"},
    ]

    rate = hit_rate_at_k(G, ground_truth, call_weight=0.5, cochange_weight=0.5, k=5)
    assert rate == 0.0  # no evaluated pairs, so defined as 0.0 rather than crashing


def test_optimization_finds_reasonable_weights():
    """
    Since b.py::bar is signaled by BOTH call and cochange edges, any
    reasonable non-zero weighting should find it — this test just
    confirms the Optuna loop runs end-to-end and produces a usable result,
    not that it finds one exact "correct" weight (there are many that work).
    """
    G = make_test_graph()
    train_pairs = [
        {"changed_function": "a.py::foo", "affected_function": "b.py::bar", "date": "2024-01-01"},
    ]

    study = run_optimization(G, train_pairs, n_trials=10, k=5)

    assert study.best_value == 1.0  # should find a perfect hit-rate on this easy case
    assert "call_weight" in study.best_params
    assert "cochange_weight" in study.best_params

"""
scoring.py

Given a unified multigraph (built by multigraph-builder) and a set of
weight parameters, computes a "blast radius" score for every neighbor
of a given function, and returns a ranked top-K list.

This is the piece Optuna tunes: the weight parameters below are exactly
what optimize.py searches over.
"""

from collections import defaultdict
from datetime import datetime
import networkx as nx

def _recency_decay(last_date_str, reference_date_str, half_life_days):
    if not last_date_str or not reference_date_str:
        return 1.0
    try:
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
        reference_date = datetime.strptime(reference_date_str, "%Y-%m-%d")
    except ValueError:
        return 1.0

    days_since = (reference_date - last_date).days
    if days_since < 0:
        days_since = 0

    if half_life_days <= 0:
        return 1.0

    return 0.5 ** (days_since / half_life_days)

def score_neighbors(
    G: nx.MultiDiGraph,
    source_function: str,
    call_weight: float,
    cochange_weight: float,
    recency_halflife_days: float = 365.0,
    reference_date: str = None,
) -> dict:
    if source_function not in G:
        return {}

    raw_cochange_signal = {}
    for _, target, data in G.out_edges(source_function, data=True):
        if data.get("edge_type") != "cochange":
            continue
        count = data.get("count", 0)
        last_date = data.get("last_date")
        decay = _recency_decay(last_date, reference_date, recency_halflife_days)
        raw_cochange_signal[target] = raw_cochange_signal.get(target, 0.0) + count * decay

    local_max = max(raw_cochange_signal.values()) if raw_cochange_signal else 1.0
    if local_max == 0:
        local_max = 1.0

    scores = defaultdict(float)

    for _, target, data in G.out_edges(source_function, data=True):
        if data.get("edge_type") == "call":
            scores[target] += call_weight * 1.0

    for target, signal in raw_cochange_signal.items():
        scores[target] += cochange_weight * (signal / local_max)

    return dict(scores)

def top_k_recommendations(
    G: nx.MultiDiGraph,
    source_function: str,
    call_weight: float,
    cochange_weight: float,
    recency_halflife_days: float = 365.0,
    reference_date: str = None,
    k: int = 5,
) -> list:
    scores = score_neighbors(
        G, source_function, call_weight, cochange_weight,
        recency_halflife_days=recency_halflife_days,
        reference_date=reference_date,
    )
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:k]

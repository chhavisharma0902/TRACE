"""
scoring.py

Given a unified multigraph (built by multigraph-builder) and a set of
weight parameters, computes a "blast radius" score for every neighbor
of a given function, and returns a ranked top-K list.

This is the piece Optuna tunes: the weight parameters below are exactly
what optimize.py searches over.
"""

from collections import defaultdict

import networkx as nx


def score_neighbors(
    G: nx.MultiDiGraph,
    source_function: str,
    call_weight: float,
    cochange_weight: float,
) -> dict:
    """
    Compute a blast-radius score for every function directly connected
    to `source_function`, combining call and co-change edges.

    Co-change counts are normalized LOCALLY — relative to
    source_function's own strongest co-change relationship — rather
    than against the graph's global maximum. Global-max normalization
    was found to crush nearly all co-change scores toward zero (since
    one unrelated, very frequently co-changed pair elsewhere in the
    graph set the scale for everyone), making call edges structurally
    dominant regardless of the weight ratio chosen. Local normalization
    ensures each function's most relevant co-change neighbor can
    compete on a comparable scale to a call edge.
    """
    if source_function not in G:
        return {}

    # Find this source function's own maximum co-change count, for local normalization
    local_cochange_counts = [
        data.get("count", 0)
        for _, _, data in G.out_edges(source_function, data=True)
        if data.get("edge_type") == "cochange"
    ]
    local_max = max(local_cochange_counts) if local_cochange_counts else 1
    if local_max == 0:
        local_max = 1

    scores = defaultdict(float)

    for _, target, data in G.out_edges(source_function, data=True):
        if data.get("edge_type") == "call":
            scores[target] += call_weight * 1.0
        elif data.get("edge_type") == "cochange":
            normalized = data.get("count", 0) / local_max
            scores[target] += cochange_weight * normalized

    return dict(scores)


def top_k_recommendations(
    G: nx.MultiDiGraph,
    source_function: str,
    call_weight: float,
    cochange_weight: float,
    k: int = 5,
) -> list:
    """
    Returns the top-k highest-scoring related functions for
    source_function, sorted descending, as a list of
    (function_id, score) tuples.
    """
    scores = score_neighbors(G, source_function, call_weight, cochange_weight)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:k]

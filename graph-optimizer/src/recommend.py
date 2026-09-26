"""
recommend.py

The recommendation engine's stable public interface. This is what the
FastAPI backend calls directly — it hides all the graph/optimization
internals (loading the graph, loading tuned weights, scoring logic)
behind one simple function.

Usage from backend:
    from recommend import RecommendationEngine

    engine = RecommendationEngine(
        graph_file="../multigraph-builder/output/unified_graph.json",
        weights_file="output/best_weights.json",
    )

    results = engine.get_recommendations("src/app.py::Flask.run", k=5)

Loading the graph and weights is deliberately done ONCE at startup
(inside __init__), not per-request.
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "multigraph-builder" / "src"))

from scoring import score_neighbors
from build_graph import load_graph


class RecommendationEngine:
    def __init__(self, graph_file, weights_file):
        self.graph_file = Path(graph_file)
        self.weights_file = Path(weights_file)

        self.G = load_graph(self.graph_file)

        with open(self.weights_file, "r", encoding="utf-8") as f:
            result = json.load(f)
        self.weights = result["best_weights"]

    def get_recommendations(self, function_id: str, k: int = 5, reference_date: str = None) -> list:
        """
        Returns the top-k related functions for function_id, ranked by
        blast-radius score, using the already-tuned weights.

        reference_date defaults to today — this is LIVE usage, unlike
        optimize.py's evaluation, which uses each ground-truth pair's
        own historical date.
        """
        if reference_date is None:
            reference_date = date.today().isoformat()

        if function_id not in self.G:
            return []

        scores = score_neighbors(
            self.G,
            function_id,
            call_weight=self.weights["call_weight"],
            cochange_weight=self.weights["cochange_weight"],
            recency_halflife_days=self.weights["recency_halflife_days"],
            reference_date=reference_date,
        )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:k]

        results = []
        for target, total_score in ranked:
            edge_types = set()
            for _, tgt, data in self.G.out_edges(function_id, data=True):
                if tgt == target:
                    edge_types.add(data.get("edge_type"))

            results.append({
                "function_id": target,
                "score": round(total_score, 4),
                "via_call": "call" in edge_types,
                "via_cochange": "cochange" in edge_types,
            })

        return results

    def get_ego_graph_data(self, function_id: str, radius: int = 2, reference_date: str = None) -> dict:
        """
        Returns a small subgraph (nodes + edges) centered on function_id,
        out to `radius` hops — the data the extension's real-time
        mind-tree widget needs. Returns plain data only, no rendering.
        """
        import networkx as nx

        if function_id not in self.G:
            return {"nodes": [], "edges": []}

        forward = nx.ego_graph(self.G, function_id, radius=radius)
        backward = nx.ego_graph(self.G.reverse(copy=False), function_id, radius=radius)

        node_ids = set(forward.nodes()) | set(backward.nodes())

        edges = []
        seen = set()
        for u, v, data in forward.edges(data=True):
            key = (u, v, data.get("edge_type"))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": u, "target": v, "edge_type": data.get("edge_type"), "count": data.get("count")})

        for u, v, data in backward.edges(data=True):
            key = (v, u, data.get("edge_type"))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": v, "target": u, "edge_type": data.get("edge_type"), "count": data.get("count")})

        return {
            "center": function_id,
            "nodes": list(node_ids),
            "edges": edges,
        }
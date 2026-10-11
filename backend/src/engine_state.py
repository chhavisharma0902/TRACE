"""Holds the recommendation engine and function resolver for the whole app.

main.py calls load() once at startup. Routes read engine_state.engine /
engine_state.resolver. The engine is read-only after load, so no lock is needed.
"""
import json
import sys
from typing import Optional

from src import config
from src.function_resolver import FunctionResolver


class MockEngine:
    """Same two methods as RecommendationEngine, answering from
    mock_data/mock_recommendations.json. Lets Member 5 build the UI before the
    real graph exists (enable with TRACE_USE_MOCK=1)."""

    G = None

    def __init__(self, mock_file):
        with open(mock_file, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def node_count(self) -> int:
        ids = set(self._data)
        for recs in self._data.values():
            ids.update(r["function_id"] for r in recs)
        return len(ids)

    def get_recommendations(self, function_id, k=5, reference_date=None):
        return list(self._data.get(function_id, []))[:k]

    def get_ego_graph_data(self, function_id, radius=2, reference_date=None):
        recs = self._data.get(function_id)
        if recs is None:
            return {"nodes": [], "edges": []}
        edges = []
        for r in recs:
            if r.get("via_call"):
                edges.append({"source": function_id, "target": r["function_id"], "edge_type": "call", "count": 1})
            if r.get("via_cochange"):
                edges.append({"source": function_id, "target": r["function_id"], "edge_type": "cochange", "count": 1})
        return {
            "center": function_id,
            "nodes": [function_id] + [r["function_id"] for r in recs],
            "edges": edges,
        }


class EngineState:
    def __init__(self):
        self.engine = None
        self.resolver: Optional[FunctionResolver] = None
        self.mode = "unavailable"  # "real" | "mock" | "unavailable"
        self.error: Optional[str] = None
        self.resolver_error: Optional[str] = None

    def load(self):
        self.engine, self.resolver = None, None
        self.mode, self.error, self.resolver_error = "unavailable", None, None
        self._load_engine()
        self._load_resolver()

    def _load_engine(self):
        if config.USE_MOCK:
            try:
                self.engine = MockEngine(config.MOCK_DATA_FILE)
                self.mode = "mock"
            except Exception as exc:
                self.error = f"mock data could not be loaded: {exc}"
            return

        missing = [str(p) for p in (config.GRAPH_FILE, config.WEIGHTS_FILE) if not p.exists()]
        if missing:
            self.error = "missing file(s): " + ", ".join(missing)
            return
        try:
            if str(config.ENGINE_SRC_DIR) not in sys.path:
                sys.path.insert(0, str(config.ENGINE_SRC_DIR))
            from recommend import RecommendationEngine  # graph-optimizer/src/recommend.py

            self.engine = RecommendationEngine(
                graph_file=config.GRAPH_FILE, weights_file=config.WEIGHTS_FILE
            )
            self.mode = "real"
        except Exception as exc:
            self.error = f"engine failed to load: {type(exc).__name__}: {exc}"

    def _load_resolver(self):
        if not config.FUNCTION_RANGES_FILE.exists():
            self.resolver_error = f"missing file: {config.FUNCTION_RANGES_FILE}"
            return
        try:
            self.resolver = FunctionResolver(config.FUNCTION_RANGES_FILE, module_files=self._module_files())
        except Exception as exc:
            self.resolver_error = f"{type(exc).__name__}: {exc}"

    def _module_files(self) -> set:
        """Files that have a '<module>' node in the graph (lines outside any function map there)."""
        graph = getattr(self.engine, "G", None)
        if graph is None:
            return set()
        suffix = "::<module>"
        return {n[: -len(suffix)] for n in graph.nodes if isinstance(n, str) and n.endswith(suffix)}

    def _node_count(self) -> Optional[int]:
        engine = self.engine
        if engine is None:
            return None
        if hasattr(engine, "node_count"):
            return engine.node_count()
        graph = getattr(engine, "G", None)
        return graph.number_of_nodes() if graph is not None else None

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "error": self.error,
            "nodes": self._node_count(),
            "resolver_loaded": self.resolver is not None,
            "resolver_error": self.resolver_error,
        }


engine_state = EngineState()

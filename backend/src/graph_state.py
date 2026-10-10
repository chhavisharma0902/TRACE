"""
Owns the in-memory graph, the tuned scoring weights, and the lock guarding
both. main.py loads it once at startup; recommend.py reads through it;
update_file.py writes through it. Nothing else touches self.graph directly.
"""
import threading
from pathlib import Path
from typing import Optional

import networkx as nx


class GraphState:
    def __init__(self):
        self.graph: nx.MultiGraph = nx.MultiGraph()
        self.lock = threading.Lock()
        self.w_ast: float = 0.5
        self.w_git: float = 0.5
        self._max_git_count: int = 1  # never 0 — avoids ZeroDivisionError below

    # ---------- startup load ----------
    def load_from_graphml(self, graph_path: Path, weights_path: Optional[Path] = None):
        """Called once from main.py's startup event."""
        with self.lock:
            self.graph = nx.read_graphml(graph_path)
            git_weights = [
                d["weight"] for _, _, d in self.graph.edges(data=True)
                if d.get("kind") == "git"
            ]
            self._max_git_count = max(git_weights) if git_weights else 1

            if weights_path and weights_path.exists():
                import json
                weights = json.loads(weights_path.read_text(encoding="utf-8"))
                self.w_ast = weights.get("w_ast", self.w_ast)
                self.w_git = weights.get("w_git", self.w_git)

    @staticmethod
    def _norm(path: str) -> str:
        return path.replace("\\", "/")

    # ---------- read path ----------
    def get_recommendations(self, file_path: str, top_n: int = 5) -> list[dict]:
        file_path = self._norm(file_path)
        with self.lock:
            if file_path not in self.graph:
                return []  # isolated / unknown file — empty list, not a crash

            scores: dict[str, float] = {}
            for neighbor in self.graph.neighbors(file_path):
                ast_exists, git_count = 0, 0
                for edge_data in self.graph.get_edge_data(file_path, neighbor).values():
                    if edge_data.get("kind") == "ast":
                        ast_exists = 1
                    elif edge_data.get("kind") == "git":
                        git_count = max(git_count, edge_data.get("weight", 0))

                normalized_git = git_count / self._max_git_count
                scores[neighbor] = (self.w_ast * ast_exists) + (self.w_git * normalized_git)

            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            return [{"file_path": f, "score": round(s, 4)} for f, s in ranked[:top_n]]

    # ---------- write path ----------
    def update_file_ast_edges(self, file_path: str, new_imports: list[str]):
        """Replaces only this file's AST edges — git edges are untouched."""
        file_path = self._norm(file_path)
        with self.lock:
            self.graph.add_node(file_path)

            for u, v, key, data in list(self.graph.edges(file_path, keys=True, data=True)):
                if data.get("kind") == "ast":
                    self.graph.remove_edge(u, v, key=key)

            for dep in new_imports:
                dep = self._norm(dep)
                self.graph.add_edge(file_path, dep, kind="ast", weight=1)


# singleton — main.py loads into this instance; both routers import and read/write it
graph_state = GraphState()
from typing import Optional

from fastapi import APIRouter, Query

from src.routes.common import require_engine, resolve_target

router = APIRouter()

CALL_EDGE_BONUS = 1000  # a direct call link outranks any amount of co-change history


def limit_ego_graph(data: dict, center: str, max_nodes: int) -> dict:
    """Keep the center plus the `max_nodes - 1` most strongly connected nodes, and only
    the edges whose both ends survive. The raw engine output can be several MB for a
    busy function, far too much for a mind-tree widget.

    Ranking: direct neighbors of the center first (call links, then co-change count),
    then other nodes by how many edges touch them.
    """
    nodes = list(data.get("nodes", []))
    edges = list(data.get("edges", []))
    total_nodes, total_edges = len(nodes), len(edges)

    direct: dict[str, int] = {}
    touching: dict[str, int] = {}
    for e in edges:
        weight = CALL_EDGE_BONUS if e.get("edge_type") == "call" else int(e.get("count") or 1)
        for node, other in ((e["source"], e["target"]), (e["target"], e["source"])):
            touching[node] = touching.get(node, 0) + 1
            if other == center:
                direct[node] = direct.get(node, 0) + weight

    others = [n for n in nodes if n != center]
    others.sort(key=lambda n: (-direct.get(n, 0), -touching.get(n, 0), n))
    kept = set(others[: max(max_nodes - 1, 0)]) | {center}

    kept_nodes = [center] + [n for n in others if n in kept]
    kept_edges = [e for e in edges if e["source"] in kept and e["target"] in kept]
    return {
        "center": center,
        "nodes": kept_nodes,
        "edges": kept_edges,
        "truncated": len(kept_nodes) < total_nodes,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
    }


@router.get("/api/ego-graph")
def ego_graph(
    function_id: Optional[str] = Query(None, description="e.g. src/app.py::Flask.run"),
    file_path: Optional[str] = Query(None, description="Workspace-relative path; use with line"),
    line: Optional[int] = Query(None, ge=1, description="1-based cursor line; use with file_path"),
    radius: int = Query(1, ge=1, le=2),
    max_nodes: int = Query(25, ge=2, le=100, description="Response is trimmed to the strongest N nodes"),
):
    engine = require_engine()
    target = resolve_target(function_id, file_path, line)
    if target is None:
        return {"center": None, "nodes": [], "edges": [], "truncated": False, "total_nodes": 0, "total_edges": 0}
    data = engine.get_ego_graph_data(target, radius=radius)
    if not data.get("nodes"):  # unknown function: the engine returns no "center" key
        return {"center": target, "nodes": [], "edges": [], "truncated": False, "total_nodes": 0, "total_edges": 0}
    return limit_ego_graph(data, data.get("center", target), max_nodes)

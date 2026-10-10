from typing import Optional

from fastapi import APIRouter, Query

from src.routes.common import require_engine, resolve_target

router = APIRouter()


@router.get("/api/ego-graph")
def ego_graph(
    function_id: Optional[str] = Query(None, description="e.g. src/app.py::Flask.run"),
    file_path: Optional[str] = Query(None, description="Workspace-relative path; use with line"),
    line: Optional[int] = Query(None, ge=1, description="1-based cursor line; use with file_path"),
    radius: int = Query(1, ge=1, le=3),
):
    engine = require_engine()
    target = resolve_target(function_id, file_path, line)
    if target is None:
        return {"center": None, "nodes": [], "edges": []}
    data = engine.get_ego_graph_data(target, radius=radius)
    # Unknown functions come back from the engine without a "center" key; always include one.
    return {
        "center": data.get("center", target),
        "nodes": data.get("nodes", []),
        "edges": data.get("edges", []),
    }

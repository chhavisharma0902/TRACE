from typing import Optional

from fastapi import APIRouter, Query

from src.routes.common import require_engine, resolve_target

router = APIRouter()


@router.get("/api/recommend")
def recommend(
    function_id: Optional[str] = Query(None, description="e.g. src/app.py::Flask.run"),
    file_path: Optional[str] = Query(None, description="Workspace-relative path; use with line"),
    line: Optional[int] = Query(None, ge=1, description="1-based cursor line; use with file_path"),
    k: int = Query(5, ge=1, le=50),
):
    engine = require_engine()
    target = resolve_target(function_id, file_path, line)
    if target is None:  # cursor is outside any function
        return {"function_id": None, "recommendations": []}
    return {"function_id": target, "recommendations": engine.get_recommendations(target, k=k)}

"""Helpers shared by the route modules."""
from typing import Optional

from fastapi import HTTPException

from src.engine_state import engine_state


def normalize_function_id(function_id: str) -> str:
    """Fix Windows slashes in the path part of 'file.py::func' (the part after :: is left alone)."""
    path, sep, name = function_id.strip().partition("::")
    return path.replace("\\", "/") + sep + name


def require_engine():
    if engine_state.engine is None:
        raise HTTPException(
            status_code=503,
            detail=f"Recommendation engine not loaded: {engine_state.error}",
        )
    return engine_state.engine


def resolve_target(function_id: Optional[str], file_path: Optional[str], line: Optional[int]) -> Optional[str]:
    """Return the function ID to look up, or None if the cursor is not inside a known function."""
    if function_id:
        return normalize_function_id(function_id)
    if file_path is None or line is None:
        raise HTTPException(status_code=400, detail="Provide either function_id, or both file_path and line.")
    if engine_state.resolver is None:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot resolve file+line, function_ranges not loaded ({engine_state.resolver_error}). Send function_id instead.",
        )
    return engine_state.resolver.resolve(file_path, line)

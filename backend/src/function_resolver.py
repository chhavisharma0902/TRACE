"""Maps (file_path, line) -> 'file.py::func_name'.

The VS Code extension only knows a file and a cursor line, while the graph is
keyed by function IDs. This module bridges the two using ast-parser's
function_ranges.json.

Expected JSON shape (file -> function -> [start_line, end_line], 1-based):
    {"src/app.py": {"Flask": [10, 300], "Flask.run": [120, 145]}}
"""
import json
from pathlib import Path
from typing import Optional


def _parse_span(span) -> tuple[int, int]:
    if isinstance(span, (list, tuple)) and len(span) == 2:
        return int(span[0]), int(span[1])
    if isinstance(span, dict):
        start = span.get("start", span.get("start_line", span.get("lineno")))
        end = span.get("end", span.get("end_line", span.get("end_lineno")))
        if start is not None and end is not None:
            return int(start), int(end)
    raise ValueError(f"unsupported line-range format: {span!r}")


def normalize_path(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


class FunctionResolver:
    def __init__(self, ranges_file):
        with open(Path(ranges_file), "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("function_ranges.json must be an object keyed by file path")

        # {normalized_path: [(start, end, func_name), ...]}
        self._ranges: dict[str, list[tuple[int, int, str]]] = {}
        for file_path, funcs in raw.items():
            if not isinstance(funcs, dict):
                raise ValueError(f"unsupported entry for {file_path!r}: expected {{name: [start, end]}}")
            spans = []
            for name, span in funcs.items():
                start, end = _parse_span(span)
                spans.append((start, end, name))
            self._ranges[normalize_path(file_path)] = spans

    def _find_key(self, path: str) -> Optional[str]:
        """Exact match first; otherwise a UNIQUE match on whole path components
        (handles 'src/app.py' vs 'shared_test_repo/src/app.py')."""
        if path in self._ranges:
            return path
        matches = [
            key for key in self._ranges
            if key.endswith("/" + path) or path.endswith("/" + key)
        ]
        return matches[0] if len(matches) == 1 else None

    def resolve(self, file_path: str, line: int) -> Optional[str]:
        """`line` is 1-based. Returns None if the line is not inside a known function."""
        key = self._find_key(normalize_path(file_path))
        if key is None:
            return None
        candidates = [(s, e, n) for s, e, n in self._ranges[key] if s <= line <= e]
        if not candidates:
            return None
        # Nested functions/methods overlap their parent: the innermost (smallest span) wins.
        _, _, name = min(candidates, key=lambda c: c[1] - c[0])
        return f"{key}::{name}"

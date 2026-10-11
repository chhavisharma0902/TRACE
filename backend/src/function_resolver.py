"""Maps (file_path, line) -> 'file.py::func_name'.

The VS Code extension only knows a file and a cursor line, while the graph is
keyed by function IDs. This module bridges the two using ast-parser's
function_ranges.json, which is FLAT and keyed by the same IDs the graph uses
(1-based, inclusive line numbers):

    {"src/app.py::Flask.run": [120, 145], "src/app.py::helper": [150, 160]}

Lines inside no function (imports, top-level code) resolve to that file's
'<module>' node, when the graph has one.
"""
import json
from pathlib import Path
from typing import Iterable, Optional

MODULE_NAME = "<module>"


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
    def __init__(self, ranges_file, module_files: Optional[Iterable[str]] = None):
        """module_files: files that have a '<module>' node in the graph."""
        with open(Path(ranges_file), "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("function_ranges.json must be an object keyed by function ID")

        # {file: [(start, end, func_name), ...]}
        self._ranges: dict[str, list[tuple[int, int, str]]] = {}
        for function_id, span in raw.items():
            file_part, sep, name = function_id.partition("::")
            if not sep or not name:
                raise ValueError(f"unsupported key {function_id!r}: expected 'path/to/file.py::function_name'")
            start, end = _parse_span(span)
            self._ranges.setdefault(normalize_path(file_part), []).append((start, end, name))

        self._module_files = {normalize_path(p) for p in (module_files or ())}
        self._known_files = set(self._ranges) | self._module_files

    def _find_key(self, path: str) -> Optional[str]:
        """Exact match first; otherwise a UNIQUE match on whole path components
        (handles 'src/app.py' vs 'shared_test_repo/src/app.py')."""
        if path in self._known_files:
            return path
        matches = [
            key for key in self._known_files
            if key.endswith("/" + path) or path.endswith("/" + key)
        ]
        return matches[0] if len(matches) == 1 else None

    def resolve(self, file_path: str, line: int) -> Optional[str]:
        """`line` is 1-based. Returns None if nothing in the graph covers that line."""
        key = self._find_key(normalize_path(file_path))
        if key is None:
            return None
        candidates = [(s, e, n) for s, e, n in self._ranges.get(key, []) if s <= line <= e]
        if candidates:
            # Nested functions/methods overlap their parent: the innermost (smallest span) wins.
            _, _, name = min(candidates, key=lambda c: c[1] - c[0])
            return f"{key}::{name}"
        if key in self._module_files:
            return f"{key}::{MODULE_NAME}"
        return None

import json

import pytest

from src.function_resolver import FunctionResolver


def make_resolver(tmp_path, data):
    f = tmp_path / "function_ranges.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return FunctionResolver(f)


RANGES = {"src/app.py": {"Flask": [1, 100], "Flask.run": [10, 20], "helper": [110, 120]}}


def test_innermost_function_wins(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src/app.py", 15) == "src/app.py::Flask.run"
    assert r.resolve("src/app.py", 50) == "src/app.py::Flask"


def test_range_boundaries_are_inclusive(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src/app.py", 10) == "src/app.py::Flask.run"
    assert r.resolve("src/app.py", 20) == "src/app.py::Flask.run"


def test_line_outside_any_function_returns_none(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src/app.py", 105) is None


def test_unknown_file_returns_none(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src/other.py", 15) is None


def test_windows_backslashes_and_dot_slash(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src\\app.py", 15) == "src/app.py::Flask.run"
    assert r.resolve("./src/app.py", 15) == "src/app.py::Flask.run"


def test_unique_suffix_match_returns_key_as_stored(tmp_path):
    r = make_resolver(tmp_path, {"shared_test_repo/src/app.py": {"f": [1, 5]}})
    assert r.resolve("src/app.py", 3) == "shared_test_repo/src/app.py::f"


def test_ambiguous_suffix_match_returns_none(tmp_path):
    r = make_resolver(tmp_path, {"a/utils.py": {"f": [1, 5]}, "b/utils.py": {"g": [1, 5]}})
    assert r.resolve("utils.py", 3) is None


def test_dict_style_spans_are_supported(tmp_path):
    r = make_resolver(tmp_path, {"x.py": {"f": {"start": 2, "end": 4}}})
    assert r.resolve("x.py", 3) == "x.py::f"


def test_unsupported_format_raises_clear_error(tmp_path):
    with pytest.raises(ValueError):
        make_resolver(tmp_path, {"x.py": {"f": "lines 1-5"}})

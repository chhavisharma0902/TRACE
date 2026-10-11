import json

import pytest

from src.function_resolver import FunctionResolver


def make_resolver(tmp_path, data, module_files=None):
    f = tmp_path / "function_ranges.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return FunctionResolver(f, module_files=module_files)


RANGES = {
    "src/app.py::Flask": [1, 100],
    "src/app.py::Flask.run": [10, 20],
    "src/app.py::helper": [110, 120],
}


def test_innermost_function_wins(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src/app.py", 15) == "src/app.py::Flask.run"
    assert r.resolve("src/app.py", 50) == "src/app.py::Flask"


def test_range_boundaries_are_inclusive(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src/app.py", 10) == "src/app.py::Flask.run"
    assert r.resolve("src/app.py", 20) == "src/app.py::Flask.run"


def test_line_outside_any_function_returns_none_without_module_node(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src/app.py", 105) is None


def test_line_outside_any_function_falls_back_to_module_node(tmp_path):
    r = make_resolver(tmp_path, RANGES, module_files={"src/app.py"})
    assert r.resolve("src/app.py", 105) == "src/app.py::<module>"
    assert r.resolve("src/app.py", 15) == "src/app.py::Flask.run"  # functions still win


def test_file_with_only_module_node_resolves(tmp_path):
    r = make_resolver(tmp_path, RANGES, module_files={"src/consts.py"})
    assert r.resolve("src/consts.py", 3) == "src/consts.py::<module>"


def test_unknown_file_returns_none(tmp_path):
    r = make_resolver(tmp_path, RANGES, module_files={"src/app.py"})
    assert r.resolve("src/other.py", 15) is None


def test_windows_backslashes_and_dot_slash(tmp_path):
    r = make_resolver(tmp_path, RANGES)
    assert r.resolve("src\\app.py", 15) == "src/app.py::Flask.run"
    assert r.resolve("./src/app.py", 15) == "src/app.py::Flask.run"


def test_unique_suffix_match_returns_key_as_stored(tmp_path):
    r = make_resolver(tmp_path, {"shared_test_repo/src/app.py::f": [1, 5]})
    assert r.resolve("src/app.py", 3) == "shared_test_repo/src/app.py::f"


def test_ambiguous_suffix_match_returns_none(tmp_path):
    r = make_resolver(tmp_path, {"a/utils.py::f": [1, 5], "b/utils.py::g": [1, 5]})
    assert r.resolve("utils.py", 3) is None


def test_dotted_function_names_keep_their_full_name(tmp_path):
    r = make_resolver(tmp_path, {"x.py::create_app.index": [20, 21]})
    assert r.resolve("x.py", 20) == "x.py::create_app.index"


def test_dict_style_spans_are_supported(tmp_path):
    r = make_resolver(tmp_path, {"x.py::f": {"start": 2, "end": 4}})
    assert r.resolve("x.py", 3) == "x.py::f"


def test_key_without_separator_raises_clear_error(tmp_path):
    with pytest.raises(ValueError, match="path/to/file.py::function_name"):
        make_resolver(tmp_path, {"x.py": {"f": [1, 5]}})


def test_unsupported_span_format_raises_clear_error(tmp_path):
    with pytest.raises(ValueError):
        make_resolver(tmp_path, {"x.py::f": "lines 1-5"})

"""
ground_truth.py

Loads the historical "ground truth" pairs used to evaluate and tune the
graph: real (changed_function -> actually_affected_function) pairs
mined from the repository's own history (e.g. via fix-commit /
bug-introducing-commit analysis).

This module expects a pre-mined ground_truth.json file as input. Mining
that file (walking git history to find fix-commit / bug-introducing
pairs, split by date) is a separate concern from optimization itself,
and can be produced by a standalone mining script sitting alongside
this one. This module only loads and splits it.

Expected ground_truth.json format:
[
    {
        "changed_function": "file_a.py::foo",
        "affected_function": "file_b.py::bar",
        "date": "2024-03-01"
    },
    ...
]
"""

import json
from pathlib import Path


def load_ground_truth(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(
            f"Ground truth file not found: {path}\n"
            "This file should contain real historical "
            "(changed_function -> affected_function) pairs, mined from "
            "the repository's fix-commit history."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def split_by_date(pairs: list, split_date: str) -> tuple:
    """
    Splits ground truth pairs into (train, test) by date, so that
    tuning happens on earlier history and evaluation happens on
    held-out, more recent history — avoiding leakage between the two.

    split_date format: "YYYY-MM-DD" (ISO format, string-sortable)
    """
    train = [p for p in pairs if p["date"] < split_date]
    test = [p for p in pairs if p["date"] >= split_date]
    return train, test

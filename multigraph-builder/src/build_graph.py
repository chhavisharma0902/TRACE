"""
build_graph.py

Merges the AST parser's structural output (ast_dependencies.json) and the
git miner's historical output (cochange.json) into a single unified
networkx.MultiDiGraph.

Each function is a node. Two edge types are added between nodes:
    - "call"      : directed, from ast_dependencies.json (function A calls function B)
    - "cochange"  : directed, from cochange.json (function A and B changed together,
                    N times, stored as edge attribute "count")

Both edge types are kept SEPARATE (not merged into a single combined weight)
so that the graph-optimizer module can independently weight them via
Bayesian optimization later. This file only builds structure — it does not
apply any weighting formula or scoring logic.
"""

import argparse
import json
import sys
from pathlib import Path

import networkx as nx


def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"\nERROR: required input file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_unified_graph(ast_data: dict, cochange_data: dict) -> nx.MultiDiGraph:
    """
    Build a unified weighted directed multigraph from AST call data and
    git co-change data.

    ast_data format:      {"file.py::func_a": ["file.py::func_b", ...], ...}
    cochange_data format: {"file.py::func_a": {"file.py::func_b": count, ...}, ...}
    """
    G = nx.MultiDiGraph()

    # --- Call edges (structural, from AST parser) ---
    call_edges_added = 0
    for source, targets in ast_data.items():
        G.add_node(source)
        for target in targets:
            G.add_node(target)
            G.add_edge(source, target, edge_type="call")
            call_edges_added += 1

    # --- Co-change edges (historical, from git miner) ---
    # cochange.json is symmetric (both directions recorded), so we add
    # directed edges as-is; the graph will naturally end up with edges
    # in both directions for each co-changed pair, which is expected.
    cochange_edges_added = 0
    for source, targets in cochange_data.items():
        G.add_node(source)
        for target, info in targets.items():
            G.add_node(target)
            count = info.get("count", 0) if isinstance(info, dict) else info
            last_date = info.get("last_date") if isinstance(info, dict) else None
            G.add_edge(source, target, edge_type="cochange", count=count, last_date=last_date)
            cochange_edges_added += 1

    print(f"Call edges added:      {call_edges_added}")
    print(f"Co-change edges added: {cochange_edges_added}")
    print(f"Total nodes:            {G.number_of_nodes()}")
    print(f"Total edges:            {G.number_of_edges()}")

    return G


def save_graph(G: nx.MultiDiGraph, output_path: Path) -> None:
    """
    Save the graph as JSON using networkx's node-link format, which is
    portable and human-readable (matches the JSON-based contracts the
    rest of the project already uses, rather than a Python-specific
    pickle format).
    """
    data = nx.node_link_data(G, edges="edges")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved unified graph to: {output_path}")


def load_graph(input_path: Path) -> nx.MultiDiGraph:
    """
    Load a previously saved unified graph back into a MultiDiGraph.
    Used by the graph-optimizer module.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return nx.node_link_graph(data, edges="edges", directed=True, multigraph=True)


def main():
    parser = argparse.ArgumentParser(
        description="Build the unified weighted multigraph from AST and co-change data."
    )
    parser.add_argument(
        "--ast-file",
        type=Path,
        default=Path("../ast-parser/output/ast_dependencies.json"),
        help="Path to ast_dependencies.json (default: ../ast-parser/output/ast_dependencies.json)",
    )
    parser.add_argument(
        "--cochange-file",
        type=Path,
        default=Path("../git-miner/output/cochange.json"),
        help="Path to cochange.json (default: ../git-miner/output/cochange.json)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("output/unified_graph.json"),
        help="Where to save the unified graph (default: output/unified_graph.json)",
    )
    args = parser.parse_args()

    print("Loading AST dependency data...")
    ast_data = load_json(args.ast_file)

    print("Loading co-change data...")
    cochange_data = load_json(args.cochange_file)

    print("\nBuilding unified graph...")
    G = build_unified_graph(ast_data, cochange_data)

    save_graph(G, args.output_file)


if __name__ == "__main__":
    main()

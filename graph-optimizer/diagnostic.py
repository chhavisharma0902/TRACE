import json
import sys
from pathlib import Path
sys.path.insert(0, "src")
sys.path.insert(0, "../multigraph-builder/src")
from build_graph import load_graph
from ground_truth import load_ground_truth, split_by_date
from optimize import hit_rate_at_k

G = load_graph(Path("../multigraph-builder/output/unified_graph.json"))
pairs = load_ground_truth(Path("data/ground_truth.json"))
_, test_pairs = split_by_date(pairs, "2023-01-01")

# Try several very different weight combos directly on the TEST set
combos = [
    (0.9, 0.1, 30),
    (0.1, 0.9, 30),
    (0.5, 0.5, 1000),
    (0.9, 0.1, 1000),
    (0.1, 0.9, 1000),
]

for call_w, cochange_w, halflife in combos:
    score = hit_rate_at_k(G, test_pairs, call_w, cochange_w, halflife, k=5)
    print(f"call={call_w}, cochange={cochange_w}, halflife={halflife} -> hit-rate={score:.4f}")
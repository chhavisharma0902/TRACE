import json
import sys
from pathlib import Path
sys.path.insert(0, "src")
sys.path.insert(0, "../multigraph-builder/src")
from build_graph import load_graph
from ground_truth import load_ground_truth
from scoring import score_neighbors

G = load_graph(Path("../multigraph-builder/output/unified_graph.json"))
pairs = load_ground_truth(Path("data/ground_truth.json"))

tied_at_top = 0
clearly_separated = 0
examples_shown = 0

for pair in pairs:
    changed = pair["changed_function"]
    affected = pair["affected_function"]
    if changed not in G:
        continue
    neighbors = set(t for _, t, _ in G.out_edges(changed, data=True))
    if affected not in neighbors:
        continue

    scores = score_neighbors(G, changed, call_weight=0.5, cochange_weight=0.5)
    if affected not in scores:
        continue

    affected_score = scores[affected]
    tied_with = sum(1 for s in scores.values() if s == affected_score)

    if tied_with > 5:
        tied_at_top += 1
        if examples_shown < 3:
            print(f"Example: {changed} -> {affected}")
            print(f"  affected_function score: {affected_score:.4f}, tied with {tied_with} other neighbors")
            examples_shown += 1
    else:
        clearly_separated += 1

print(f"\nPairs where target is tied with 5+ other neighbors at the same score: {tied_at_top}")
print(f"Pairs where target has a distinct, separable score: {clearly_separated}")
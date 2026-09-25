"""
optimize.py

Runs Bayesian optimization (via Optuna) to find the call_weight and
cochange_weight values that maximize hit-rate@top-5 against real
historical ground truth — instead of hand-picking these weights.

This is the module's core contribution: everything else in this
project (multigraph-builder, scoring.py) exists to make this
optimization loop possible.
"""

import argparse
import json
import sys
from pathlib import Path

import optuna

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "multigraph-builder" / "src"))

from scoring import top_k_recommendations
from ground_truth import load_ground_truth, split_by_date
from build_graph import load_graph


def hit_rate_at_k(G, ground_truth_pairs, call_weight, cochange_weight, recency_halflife_days=365.0, k=5):
    """
    For each (changed_function, affected_function) pair in ground_truth_pairs,
    checks whether affected_function appears in the top-k recommendations
    for changed_function under the given weights.

    Returns the fraction of pairs that were a "hit" (0.0 to 1.0).
    """
    if not ground_truth_pairs:
        return 0.0

    hits = 0
    evaluated = 0

    for pair in ground_truth_pairs:
        changed = pair["changed_function"]
        affected = pair["affected_function"]
        reference_date = pair.get("date")

        if changed not in G:
            continue

        evaluated += 1
        recommendations = top_k_recommendations(
            G, changed, call_weight, cochange_weight,
            recency_halflife_days=recency_halflife_days,
            reference_date=reference_date,
            k=k,
        )
        recommended_ids = {func_id for func_id, _score in recommendations}

        if affected in recommended_ids:
            hits += 1

    if evaluated == 0:
        return 0.0

    return hits / evaluated


def make_objective(G, train_pairs, k=5):
    """
    Returns an Optuna objective function closed over the graph and
    training ground truth, so Optuna only needs to supply weight values.
    """

    def objective(trial):
        call_weight = trial.suggest_float("call_weight", 0.0, 1.0)
        cochange_weight = trial.suggest_float("cochange_weight", 0.0, 1.0)
        recency_halflife_days = trial.suggest_float("recency_halflife_days", 7.0, 1825.0, log=True)

        return hit_rate_at_k(G, train_pairs, call_weight, cochange_weight, recency_halflife_days, k=k)

    return objective


def run_optimization(G, train_pairs, n_trials=100, k=5):
    study = optuna.create_study(direction="maximize")
    objective = make_objective(G, train_pairs, k=k)
    study.optimize(objective, n_trials=n_trials)
    return study


def evaluate_baseline(G, test_pairs, k=5):
    """
    A simple fixed-weight baseline (equal weighting), used for
    comparison against the Optuna-tuned result — this is what
    demonstrates the optimization is actually adding value.
    """
    return hit_rate_at_k(G, test_pairs, call_weight=0.5, cochange_weight=0.5, recency_halflife_days=1e9, k=k)


def main():
    parser = argparse.ArgumentParser(
        description="Tune graph edge weights via Bayesian optimization (Optuna)."
    )
    parser.add_argument(
        "--graph-file",
        type=Path,
        default=Path("../multigraph-builder/output/unified_graph.json"),
    )
    parser.add_argument(
        "--ground-truth-file",
        type=Path,
        default=Path("data/ground_truth_example.json"),
    )
    parser.add_argument(
        "--split-date",
        type=str,
        default="2024-01-01",
        help="ISO date (YYYY-MM-DD): pairs before this are used for tuning, "
        "pairs on/after this are held out for testing.",
    )
    parser.add_argument("--n-trials", type=int, default=100)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("output/best_weights.json"),
    )
    args = parser.parse_args()

    print(f"Loading unified graph from {args.graph_file}...")
    G = load_graph(args.graph_file)
    print(f"Graph loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    print(f"\nLoading ground truth from {args.ground_truth_file}...")
    all_pairs = load_ground_truth(args.ground_truth_file)
    train_pairs, test_pairs = split_by_date(all_pairs, args.split_date)
    print(f"Train pairs (before {args.split_date}): {len(train_pairs)}")
    print(f"Test pairs (on/after {args.split_date}):  {len(test_pairs)}")

    if not train_pairs:
        print("\nERROR: no training pairs available. Check your ground truth file and split date.", file=sys.stderr)
        sys.exit(1)

    print(f"\nRunning Optuna optimization ({args.n_trials} trials)...")
    study = run_optimization(G, train_pairs, n_trials=args.n_trials, k=args.k)

    best_weights = study.best_params
    best_train_score = study.best_value

    print(f"\nBest weights found: {best_weights}")
    print(f"Best hit-rate@{args.k} on training data: {best_train_score:.3f}")

    # Evaluate on held-out test data with the tuned weights
    tuned_test_score = hit_rate_at_k(
        G, test_pairs,
        call_weight=best_weights["call_weight"],
        cochange_weight=best_weights["cochange_weight"],
        recency_halflife_days=best_weights["recency_halflife_days"],
        k=args.k,
    )
    baseline_test_score = evaluate_baseline(G, test_pairs, k=args.k)

    print(f"\nHeld-out test set (unseen during tuning):")
    print(f"  Tuned weights hit-rate@{args.k}:    {tuned_test_score:.3f}")
    print(f"  Fixed baseline (0.5/0.5) hit-rate@{args.k}: {baseline_test_score:.3f}")

    result = {
        "best_weights": best_weights,
        "train_hit_rate": best_train_score,
        "test_hit_rate_tuned": tuned_test_score,
        "test_hit_rate_baseline": baseline_test_score,
        "n_trials": args.n_trials,
        "k": args.k,
    }

    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\nSaved results to: {args.output_file}")


if __name__ == "__main__":
    main()

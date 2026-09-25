# graph-optimizer

## What this module does

Takes the unified multigraph produced by `multigraph-builder` and
learns how much to trust each of its two edge types — `call` edges
(structural) and `cochange` edges (historical) — by running **Bayesian
optimization (via Optuna)** against real historical ground truth,
instead of hand-picking a fixed formula.

This is the project's core research contribution: prior work either
hand-picks these weights (a simple `0.5 * call + 0.5 * cochange`
formula) or learns them via fixed statistical methods (e.g. LCIP).
Here, the weights are found by *searching* the weight space to
maximize a real, measurable outcome — hit-rate@top-5 against actual
historical regressions.

## How it works

1. **`scoring.py`** — given a function and a candidate set of weights
   (`call_weight`, `cochange_weight`), computes a blast-radius score
   for every directly connected neighbor, and returns the top-k ranked
   list. Co-change counts are normalized (against the graph's max
   count) before weighting, so one very frequently co-changed pair
   can't dominate the score on an unbounded raw scale.

2. **`ground_truth.py`** — loads real
   `(changed_function -> affected_function)` pairs, mined from the
   repository's own fix-commit history, and splits them by date into
   train/test sets (earlier history for tuning, later history held
   out for evaluation, avoiding leakage).

3. **`optimize.py`** — the main entry point. Defines an Optuna
   objective function that: takes a candidate `(call_weight,
   cochange_weight)` pair → scores all training ground-truth pairs
   using `scoring.py` → returns the resulting hit-rate@top-5. Optuna
   runs many trials, searching for the weights that maximize this
   score. The best weights found are then evaluated on the **held-out
   test set** (unseen during tuning) and compared against a fixed
   0.5/0.5 baseline, to demonstrate the optimization is adding real
   value, not just overfitting to the training data.

## Mining real ground truth (`mine_ground_truth.py`)

`ground_truth.py` only *loads* a `ground_truth.json` file — it doesn't
create one. `mine_ground_truth.py` is what actually produces real data,
using an **SZZ-style approach** (Śliwerski, Zimmermann, Zeller): the
standard software-engineering-research technique for identifying
bug-introducing commits.

How it works:
1. Finds "fix commits" via commit message keywords (fix, bug, error,
   issue, resolve).
2. For each fix commit, finds the exact lines it changed.
3. Runs `git blame` on those same lines, but on the **parent** commit
   (before the fix) — revealing which earlier commit last touched
   them. That earlier commit is treated as the bug-introducing commit.
4. If that bug-introducing commit touched other functions *in the same
   commit*, those functions are paired with whatever the later fix
   commit changed: `(function from intro commit) -> (function fixed later)`.

```bash
python src/mine_ground_truth.py <path-to-repo> \
    --function-ranges ../ast-parser/output/function_ranges.json \
    --output data/ground_truth.json \
    --max-fix-commits 200   # optional: for a faster first test run
```

**Known limitation, by design of the SZZ technique itself**: a pair
is only found when the bug-introducing commit touched *multiple
functions together*, and the fix commit re-touches the *exact same
lines*. It does not catch the broader case where a change in one
function later required genuinely new lines elsewhere. This is a real
gap in classic SZZ — and part of why this project also uses the
co-change graph as a second, complementary signal, since co-change
captures broader "tend to change around the same time" patterns that
strict blame-tracing misses.

## What this module does NOT do

- No graph construction — that's `multigraph-builder`'s job; this
  module only loads its output (`unified_graph.json`).

## Input contracts (consumed)

- `multigraph-builder/output/unified_graph.json`
- `data/ground_truth.json` — see `data/ground_truth.example.json` for
  the expected shape; replace with real mined data before running for
  real results.

## Output

- `output/best_weights.json` — the best weights Optuna found, plus
  train/test hit-rate scores (tuned vs. fixed baseline), for direct
  use in the synopsis/evaluation section and for the recommendation
  engine to load at runtime.

## Usage

```bash
pip install -r requirements.txt

python src/optimize.py \
    --graph-file ../multigraph-builder/output/unified_graph.json \
    --ground-truth-file data/ground_truth.json \
    --split-date 2024-01-01 \
    --n-trials 100 \
    --k 5
```

## Tests

```bash
python -m pytest tests/
```

Tests use small synthetic graphs and ground-truth data (not a real
repo), so they run fast and don't depend on the earlier pipeline
stages having been run first.

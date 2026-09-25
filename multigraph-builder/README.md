# multigraph-builder

## What this module does

Merges the AST parser's output (`ast_dependencies.json`) and the git
miner's output (`cochange.json`) into a single **unified weighted
directed multigraph** (`networkx.MultiDiGraph`).

Every function found by either upstream module becomes a node. Two
distinct edge types are added between nodes, kept separate rather than
combined into one number:

- **`call`** edges — structural, from AST parsing: function A calls
  function B.
- **`cochange`** edges — historical, from git mining: function A and
  function B changed together in the same commit N times (`count`
  attribute holds N).

Because the graph is a *multi*graph, a single pair of functions can
have both a `call` edge and a `cochange` edge at the same time,
retrievable independently. This is deliberate: this module does **not**
decide how much each edge type should matter — it only builds the
structure. Weighting and scoring is the responsibility of the
`graph-optimizer` module, which consumes this module's output.

## What this module does NOT do

- No weighting formula, no scoring, no Bayesian optimization — that
  all lives in `graph-optimizer`.
- No AST parsing or git mining itself — this only merges the two
  upstream JSON outputs.

## Input contracts (consumed)

- `ast-parser/output/ast_dependencies.json`
- `git-miner/output/cochange.json`

Both are produced by their respective sibling modules — see
`docs/data_contracts.md` at the repo root for the exact format.

## Output

- `output/unified_graph.json` — the merged graph, saved in networkx's
  node-link JSON format (portable, human-readable, loadable back into
  a `MultiDiGraph` via `load_graph()`).

## Usage

```bash
pip install -r requirements.txt

python src/build_graph.py \
    --ast-file ../ast-parser/output/ast_dependencies.json \
    --cochange-file ../git-miner/output/cochange.json \
    --output-file output/unified_graph.json
```

(Default paths already point at the sibling modules' standard output
locations, so running with no arguments works if the standard repo
layout is used.)

## Tests

```bash
python -m pytest tests/
```

Tests use small synthetic data (not a real repo) so they run fast and
don't depend on the AST parser or git miner having been run first.

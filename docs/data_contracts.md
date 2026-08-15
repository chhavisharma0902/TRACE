# Data Contracts

Exact data formats each module produces and consumes.
Do not change without team agreement — see freeze note at bottom.

## Node ID format (used everywhere)

    relative/path/to/file.py::function_name
    relative/path/to/file.py::ClassName.method_name

- Relative to repo root, forward slashes only (even on Windows)
- No leading "./"

---

## 1. AST Parser Output
Produced by: ast-parser (Member 2) → Consumed by: graph-optimizer (Member 3)
File: `ast-parser/output/ast_dependencies.json`

    {
      "src/auth.py::login": ["src/models.py::User.save", "src/utils.py::helper.hash_password"],
      "src/models.py::User.save": []
    }

- Keys = every function/method found (even if it calls nothing)
- Values = list of function IDs it directly calls
- .py files only, excluding venvs/third-party packages

---

## 2. Git Miner Output
Produced by: git-miner (Member 1) → Consumed by: graph-optimizer (Member 3)
File: `git-miner/output/cochange.json`

    {
      "src/auth.py::login": {"src/models.py::User.save": 8, "src/utils.py::helper.hash_password": 3},
      "src/models.py::User.save": {"src/auth.py::login": 8}
    }

- Keys/nested keys = function IDs (same format as above)
- Values = raw co-change counts (integers), not normalized
- Commits touching more than 15 files are skipped (mega-commit filter)
- Only .py file changes considered

---

## 3. Graph Optimizer Output
Produced by: graph-optimizer (Member 3) → Consumed by: backend (Member 4)
File: `graph-optimizer/config/best_weights.json`

    {
      "call_weight": 0.62,
      "cochange_weight": 0.38,
      "recency_halflife_days": 21
    }

- Weights are floats, regenerated each time Optuna tuning is re-run

---

## 4. Recommendation API Response
Produced by: backend (Member 4) → Consumed by: vscode-extension (Member 5)
Endpoint: `GET /api/recommend?function_id=<node_id>`

    {
      "function_id": "src/auth.py::login",
      "recommendations": [
        {"function_id": "src/models.py::User.save", "score": 0.91},
        {"function_id": "src/utils.py::helper.hash_password", "score": 0.74}
      ]
    }

- Sorted by score, descending
- Top 5 only (matches hit-rate@top-5 evaluation)

---

## Freeze note

> Contracts frozen as of [DATE]. Changes require a PR against this file, with sign-off from the consuming member before merging.
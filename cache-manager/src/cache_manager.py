"""
cache_manager.py

Multi-repo caching layer. Backend calls ensure_fresh(repo_path, ...) when
a developer opens a repo — this checks whether a cached graph/weights
already exist AND are still up to date with the repo's current commit,
rebuilding only if needed.

Reuses the same staleness-check pattern already used inside
git-miner's own cache (compare stored commit hash vs. current HEAD),
just applied one level up: across repos, not within one.

Cache layout on disk:
    ~/.trace/cache/<hash-of-repo-path>/
        meta.json            {"repo_path", "last_commit", "last_built", "last_accessed"}
        unified_graph.json
        best_weights.json
        ground_truth.json    (mined once per repo, reused across rebuilds)
"""

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

CACHE_ROOT = Path.home() / ".trace" / "cache"
MAX_CACHE_AGE_DAYS = 30

def _repo_cache_dir(repo_path: str) -> Path:
    resolved = str(Path(repo_path).resolve())
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]
    return CACHE_ROOT / digest


def _get_current_commit(repo_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Not a valid git repository: {repo_path}\n{result.stderr.strip()}")
    return result.stdout.strip()


def _load_meta(cache_dir: Path) -> dict:
    meta_file = cache_dir / "meta.json"
    if not meta_file.exists():
        return {}
    with open(meta_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_meta(cache_dir: Path, meta: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def is_cache_fresh(repo_path: str) -> bool:
    """
    True only if: a cache exists for this exact repo path, both
    required output files are present, AND the repo's current commit
    matches what was cached (no new commits since last build).
    """
    cache_dir = _repo_cache_dir(repo_path)
    meta = _load_meta(cache_dir)
    if not meta:
        return False

    required_files = ["unified_graph.json", "best_weights.json"]
    if not all((cache_dir / f).exists() for f in required_files):
        return False

    try:
        current_commit = _get_current_commit(repo_path)
    except RuntimeError:
        return False

    return (
        meta.get("last_commit") == current_commit
        and meta.get("repo_path") == str(Path(repo_path).resolve())
    )


def get_cached_files(repo_path: str) -> dict:
    cache_dir = _repo_cache_dir(repo_path)
    return {
        "graph_file": cache_dir / "unified_graph.json",
        "weights_file": cache_dir / "best_weights.json",
        "cache_dir": cache_dir,
    }


def touch_last_accessed(repo_path: str) -> None:
    cache_dir = _repo_cache_dir(repo_path)
    meta = _load_meta(cache_dir)
    if meta:
        meta["last_accessed"] = date.today().isoformat()
        _save_meta(cache_dir, meta)


def _run(cmd: list, cwd: Path) -> str:
    result = subprocess.run(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def rebuild_cache(repo_path: str, project_root: Path, n_trials: int = 100) -> dict:
    """
    Runs the full pipeline for repo_path (AST parsing, git mining,
    graph building, ground-truth mining if not already cached,
    optimization) and saves all resulting files into this repo's
    dedicated cache folder.

    project_root: path to the TRACE repo root (containing
    ast-parser/, git-miner/, multigraph-builder/, graph-optimizer/).
    """
    cache_dir = _repo_cache_dir(repo_path)
    cache_dir.mkdir(parents=True, exist_ok=True)

    ast_parser_dir = project_root / "ast-parser"
    git_miner_dir = project_root / "git-miner"
    multigraph_dir = project_root / "multigraph-builder"
    optimizer_dir = project_root / "graph-optimizer"

    print(f"[cache] Rebuilding for {repo_path} ...")

    print("[cache] Running AST parser...")
    _run([sys.executable, "src/main.py", repo_path], cwd=ast_parser_dir)

    print("[cache] Running git miner...")
    _run([sys.executable, "git_miner.py", repo_path], cwd=git_miner_dir)

    print("[cache] Building unified graph...")
    unified_graph_path = cache_dir / "unified_graph.json"
    _run([
        sys.executable, "src/build_graph.py",
        "--ast-file", str(ast_parser_dir / "output" / "ast_dependencies.json"),
        "--cochange-file", str(git_miner_dir / "output" / "cochange.json"),
        "--output-file", str(unified_graph_path),
    ], cwd=multigraph_dir)

    # Ground truth mining is the slowest step (walks full history + git
    # blame per hunk) — only run it once per repo, reuse on rebuilds
    # triggered by new commits, rather than re-mining from scratch
    # every single time a developer opens the repo again.
    ground_truth_path = cache_dir / "ground_truth.json"
    if not ground_truth_path.exists():
        print("[cache] Mining ground truth (first time for this repo — this is the slow step)...")
        _run([
            sys.executable, "src/mine_ground_truth.py", repo_path,
            "--function-ranges", str(ast_parser_dir / "output" / "function_ranges.json"),
            "--output", str(ground_truth_path),
        ], cwd=optimizer_dir)
    else:
        print("[cache] Reusing existing ground truth for this repo.")

    print("[cache] Running Bayesian optimization...")
    best_weights_path = cache_dir / "best_weights.json"
    _run([
        sys.executable, "src/optimize.py",
        "--graph-file", str(unified_graph_path),
        "--ground-truth-file", str(ground_truth_path),
        "--n-trials", str(n_trials),
        "--output-file", str(best_weights_path),
    ], cwd=optimizer_dir)

    current_commit = _get_current_commit(repo_path)
    meta = {
        "repo_path": str(Path(repo_path).resolve()),
        "last_commit": current_commit,
        "last_built": date.today().isoformat(),
        "last_accessed": date.today().isoformat(),
    }
    _save_meta(cache_dir, meta)

    print(f"[cache] Done. Cached at {cache_dir}")
    return get_cached_files(repo_path)


def ensure_fresh(repo_path: str, project_root: Path, n_trials: int = 100) -> dict:
    """
    Main entry point for backend. Returns {"graph_file", "weights_file",
    "cache_dir"} ready to pass straight into RecommendationEngine —
    rebuilding the pipeline only if the cache is missing or the repo
    has moved to a new commit since it was last built.
    """
    if is_cache_fresh(repo_path):
        touch_last_accessed(repo_path)
        return get_cached_files(repo_path)
    return rebuild_cache(repo_path, project_root, n_trials=n_trials)


def evict_stale_caches(max_age_days: int = MAX_CACHE_AGE_DAYS) -> list:
    """
    Deletes cache folders not accessed in max_age_days. Call this
    occasionally (e.g. once on backend startup) to avoid unbounded
    disk growth across many repos over time. Returns the list of
    evicted cache directories.
    """
    if not CACHE_ROOT.exists():
        return []

    cutoff = datetime.today().date() - timedelta(days=max_age_days)
    evicted = []

    for entry in CACHE_ROOT.iterdir():
        if not entry.is_dir():
            continue
        meta = _load_meta(entry)
        last_accessed_str = meta.get("last_accessed")
        if not last_accessed_str:
            continue
        try:
            last_accessed = datetime.strptime(last_accessed_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if last_accessed < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            evicted.append(str(entry))

    return evicted
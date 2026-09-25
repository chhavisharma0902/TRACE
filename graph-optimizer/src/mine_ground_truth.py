"""
mine_ground_truth.py

Mines REAL (changed_function -> affected_function) ground truth pairs
from a repository's git history, using an SZZ-style approach
(Sliwerski, Zimmermann, Zeller): find fix commits, then trace back via
`git blame` to the commit that last touched the fixed lines — that
earlier commit is treated as the "bug-introducing" commit.

The resulting pair models: "if a developer had made the earlier change
(to function A), would our system have correctly flagged the function
that later needed fixing (function B) as worth reviewing?"

This is a heuristic, not ground truth in an absolute sense — commit
messages are an imperfect signal of "this was a bug fix", and blame
attribution has the same "current snapshot" line-range approximation
caveat as git-miner. It is, however, the standard, well-established
technique for this exact problem in the software engineering research
literature, and is far better than hand-written or synthetic pairs.

Usage:
    python src/mine_ground_truth.py <repo_path> \
        --function-ranges ../ast-parser/output/function_ranges.json \
        --output data/ground_truth.json
"""

import argparse
import json
import re
import subprocess
import sys
from bisect import bisect_right
from pathlib import Path

FIX_KEYWORDS = re.compile(
    r"\b(fix|fixes|fixed|bug|bugfix|error|issue|resolve|resolves|resolved)\b",
    re.IGNORECASE,
)

MAX_FILES_PER_FIX_COMMIT = 10  # skip large, noisy fix commits (e.g. mass refactors)


def run_git(repo_path, args):
    command = ["git", "-C", str(repo_path), *args]
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def load_function_ranges(path):
    with open(path, "r", encoding="utf-8") as f:
        ranges_data = json.load(f)

    file_ranges = {}
    for key, value in ranges_data.items():
        if "::" not in key:
            continue
        start, end = value
        file_path, func_name = key.split("::", 1)
        file_path = file_path.replace("\\", "/")
        file_ranges.setdefault(file_path, {})[func_name] = (int(start), int(end))

    sorted_ranges = {}
    for file_path, functions in file_ranges.items():
        ranges = sorted(
            [(s, e, name) for name, (s, e) in functions.items()],
            key=lambda item: (item[0], item[1]),
        )
        sorted_ranges[file_path] = {
            "starts": [r[0] for r in ranges],
            "ranges": ranges,
        }
    return sorted_ranges


def line_to_function(line_num, prepared_ranges):
    if not prepared_ranges:
        return "<module>"
    starts = prepared_ranges["starts"]
    ranges = prepared_ranges["ranges"]
    index = bisect_right(starts, line_num) - 1
    if index < 0:
        return "<module>"
    best_match, best_size = None, None
    while index >= 0:
        start, end, name = ranges[index]
        if start > line_num:
            index -= 1
            continue
        if end < line_num:
            break
        size = end - start
        if best_size is None or size < best_size:
            best_match, best_size = name, size
        index -= 1
    return best_match or "<module>"


def find_fix_commits(repo_path):
    """Return [(commit_hash, date), ...] for commits whose message suggests a bug fix."""
    output = run_git(repo_path, ["log", "--format=%H|%ad|%s", "--date=short", "--", "*.py"])
    fix_commits = []
    for line in output.splitlines():
        if "|" not in line:
            continue
        commit_hash, date, message = line.split("|", 2)
        if FIX_KEYWORDS.search(message):
            fix_commits.append((commit_hash, date))
    return fix_commits


def get_changed_hunks(repo_path, commit_hash):
    """
    Returns per-file lists of (old_start, old_count, new_start, new_count)
    for a commit's diff against its parent, restricted to .py files.
    """
    diff_text = run_git(
        repo_path,
        ["show", "--format=", "--unified=0", commit_hash, "--", "*.py"],
    )

    hunks = {}
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip().replace("\\", "/")
        elif line.startswith("+++ /dev/null"):
            current_file = None
        elif line.startswith("@@ ") and current_file:
            try:
                header = line.split("@@", 2)[1].strip()
                old_part, new_part = header.split(" ")
                old_start_str = old_part[1:]  # strip leading '-'
                new_start_str = new_part[1:]  # strip leading '+'

                old_start, old_count = (
                    (int(x) for x in old_start_str.split(","))
                    if "," in old_start_str else (int(old_start_str), 1)
                )
                new_start, new_count = (
                    (int(x) for x in new_start_str.split(","))
                    if "," in new_start_str else (int(new_start_str), 1)
                )

                hunks.setdefault(current_file, []).append(
                    (old_start, old_count, new_start, new_count)
                )
            except (ValueError, IndexError):
                continue

    return hunks


def blame_old_lines(repo_path, parent_hash, file_path, old_start, old_count):
    """
    Runs git blame on the PARENT commit for the given old line range,
    returning the set of commit hashes that last touched those lines
    (i.e. candidate bug-introducing commits).
    """
    if old_count <= 0:
        return set()

    end_line = old_start + old_count - 1
    try:
        output = run_git(
            repo_path,
            ["blame", "-l", "-L", f"{old_start},{end_line}", parent_hash, "--", file_path],
        )
    except RuntimeError:
        return set()

    commits = set()
    for line in output.splitlines():
        commit_hash = line.split(" ", 1)[0].lstrip("^")
        if commit_hash:
            commits.add(commit_hash)
    return commits


def get_commit_date(repo_path, commit_hash):
    output = run_git(repo_path, ["show", "-s", "--format=%ad", "--date=short", commit_hash])
    return output.strip()


def mine(repo_path, function_ranges, max_fix_commits=None):
    MAX_PAIRS_PER_FIX_COMMIT = 20  # cap noisy fix commits from flooding the output
    fix_commits = find_fix_commits(repo_path)
    if max_fix_commits:
        fix_commits = fix_commits[:max_fix_commits]

    print(f"Found {len(fix_commits)} candidate fix commits")

    pairs = []
    seen_pairs = set()

    for i, (fix_hash, fix_date) in enumerate(fix_commits):
        if (i + 1) % 25 == 0:
            print(f"Processed {i + 1}/{len(fix_commits)} fix commits, {len(pairs)} pairs found so far...")

        try:
            hunks_by_file = get_changed_hunks(repo_path, fix_hash)
        except RuntimeError:
            continue

        if len(hunks_by_file) > MAX_FILES_PER_FIX_COMMIT:
            continue

        parent_hash = f"{fix_hash}^"

        # Functions touched by the FIX (the "affected_function" side)
        fixed_functions = set()
        for file_path, hunks in hunks_by_file.items():
            ranges_for_file = function_ranges.get(file_path, {})
            for old_start, old_count, new_start, new_count in hunks:
                for line_num in range(new_start, new_start + max(new_count, 1)):
                    fixed_functions.add(f"{file_path}::{line_to_function(line_num, ranges_for_file)}")

        pairs_from_this_fix = 0  # NEW: track how many pairs this one fix commit has produced

        # Functions touched by whichever earlier commit(s) last touched
        # those same lines before the fix (the "changed_function" / bug-introducing side)
        for file_path, hunks in hunks_by_file.items():
            ranges_for_file = function_ranges.get(file_path, {})
            for old_start, old_count, new_start, new_count in hunks:
                if old_count == 0:
                    continue  # pure addition, nothing to blame in the parent

                if pairs_from_this_fix >= MAX_PAIRS_PER_FIX_COMMIT:
                    break  # NEW: stop processing more hunks for this fix commit

                intro_commits = blame_old_lines(repo_path, parent_hash, file_path, old_start, old_count)

                for intro_hash in intro_commits:
                    if intro_hash == fix_hash:
                        continue

                    if pairs_from_this_fix >= MAX_PAIRS_PER_FIX_COMMIT:
                        break  # NEW: stop processing more intro commits

                    try:
                        intro_hunks = get_changed_hunks(repo_path, intro_hash)
                        intro_date = get_commit_date(repo_path, intro_hash)
                    except RuntimeError:
                        continue

                    # Skip large intro commits too — a big refactor here would
                    # otherwise pair with EVERY function touched in the fix,
                    # causing combinatorial explosion (this was producing
                    # ~340 pairs per fix commit before this guard).
                    if len(intro_hunks) > MAX_FILES_PER_FIX_COMMIT:
                        continue

                    for intro_file, i_hunks in intro_hunks.items():
                        intro_ranges = function_ranges.get(intro_file, {})
                        for _, _, i_new_start, i_new_count in i_hunks:
                            for line_num in range(i_new_start, i_new_start + max(i_new_count, 1)):
                                changed_func = f"{intro_file}::{line_to_function(line_num, intro_ranges)}"

                                for affected_func in fixed_functions:
                                    if changed_func == affected_func:
                                        continue

                                    # Skip pairs involving <module> nodes — these are
                                    # top-level file code (imports, constants, entry
                                    # points), not real function-to-function
                                    # relationships, and were found to dominate
                                    # (~82%) the mined dataset, diluting the
                                    # genuine signal.
                                    if "::<module>" in changed_func or "::<module>" in affected_func:
                                        continue
                                    
                                    if pairs_from_this_fix >= MAX_PAIRS_PER_FIX_COMMIT:
                                        break  # NEW: stop adding more pairs from this fix

                                    key = (changed_func, affected_func)
                                    if key in seen_pairs:
                                        continue
                                    seen_pairs.add(key)
                                    pairs.append({
                                        "changed_function": changed_func,
                                        "affected_function": affected_func,
                                        "date": intro_date,
                                    })
                                    pairs_from_this_fix += 1  # NEW: increment the counter

    return pairs


def main():
    parser = argparse.ArgumentParser(description="Mine SZZ-style ground truth pairs from git history.")
    parser.add_argument("repo_path", help="Path to the git repository")
    parser.add_argument(
        "--function-ranges",
        default="../ast-parser/output/function_ranges.json",
        help="Path to function_ranges.json",
    )
    parser.add_argument("--output", default="data/ground_truth.json")
    parser.add_argument(
        "--max-fix-commits",
        type=int,
        default=None,
        help="Limit how many fix commits to process (useful for a quick test run first)",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo_path)

    print("Loading function ranges...")
    function_ranges = load_function_ranges(args.function_ranges)

    print("Mining ground truth pairs (this can take a while on large histories)...")
    pairs = mine(repo_path, function_ranges, max_fix_commits=args.max_fix_commits)

    print(f"\nTotal ground truth pairs mined: {len(pairs)}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, indent=2)

    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()

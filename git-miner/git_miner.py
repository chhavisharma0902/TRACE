import os
import json
import sys
import subprocess
from itertools import combinations
from bisect import bisect_right


# ==================================================
# SETTINGS
# ==================================================

MAX_FILES_PER_COMMIT = 15
MAX_FUNCTIONS_PER_COMMIT = 100

CACHE_FILE_NAME = "cochange_cache.json"
OUTPUT_FILE_NAME = "cochange.json"


# ==================================================
# REPOSITORY INPUT
# ==================================================

if len(sys.argv) < 2:
    print("Usage: python git_miner.py <repository_path_or_url>")
    sys.exit(1)

REPO_PATH = sys.argv[1]


# ==================================================
# PATHS
# ==================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

AST_FILE = os.path.join(PROJECT_ROOT, "ast-parser", "output", "ast_dependencies.json")
RANGES_FILE = os.path.join(PROJECT_ROOT, "ast-parser", "output", "function_ranges.json")

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_FILE = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME)
CACHE_FILE = os.path.join(OUTPUT_DIR, CACHE_FILE_NAME)


# ==================================================
# LOAD AST FUNCTION INFORMATION
# ==================================================

for required_file, label in [
    (AST_FILE, "ast_dependencies.json"),
    (RANGES_FILE, "function_ranges.json")
]:
    if not os.path.exists(required_file):
        print(f"\nERROR: {label} not found at {required_file}")
        print("Ask the AST Parser member to re-run main.py — it should also output function_ranges.json")
        sys.exit(1)

with open(RANGES_FILE, "r", encoding="utf-8") as f:
    ranges_data = json.load(f)


# ==================================================
# BUILD SORTED FILE -> FUNCTION RANGE MAPPING
# ==================================================

file_function_ranges = {}

for key, value in ranges_data.items():
    try:
        start, end = value
    except (TypeError, ValueError):
        continue

    if "::" not in key:
        continue

    file_path, func_name = key.split("::", 1)
    file_path = file_path.replace("\\", "/")

    file_function_ranges.setdefault(file_path, {})[func_name] = (int(start), int(end))

sorted_function_ranges = {}

for file_path, functions in file_function_ranges.items():
    ranges = [
        (start, end, func_name)
        for func_name, (start, end) in functions.items()
    ]
    ranges.sort(key=lambda item: (item[0], item[1]))

    sorted_function_ranges[file_path] = {
        "starts": [item[0] for item in ranges],
        "ranges": ranges
    }


# ==================================================
# FUNCTION LOOKUP (binary search)
# ==================================================

def line_to_function(line_num, prepared_ranges):
    """
    Find the smallest function range containing line_num.
    Returns the function name (matching AST parser's dotted
    ClassName.method_name format), or '<module>' if outside
    any function.
    """
    if not prepared_ranges:
        return "<module>"

    starts = prepared_ranges["starts"]
    ranges = prepared_ranges["ranges"]

    index = bisect_right(starts, line_num) - 1
    if index < 0:
        return "<module>"

    best_match = None
    best_size = None

    while index >= 0:
        start, end, func_name = ranges[index]

        if start > line_num:
            index -= 1
            continue

        if end < line_num:
            break

        size = end - start
        if best_size is None or size < best_size:
            best_match = func_name
            best_size = size

        index -= 1

    return best_match or "<module>"


# ==================================================
# GIT COMMAND HELPER
# ==================================================

def run_git(args):
    command = ["git", "-C", REPO_PATH, *args]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
    except FileNotFoundError:
        print("\nERROR: Git was not found on PATH. Please install Git and make sure 'git' works from the terminal.")
        sys.exit(1)

    if result.returncode != 0:
        raise RuntimeError(f"Git command failed:\ngit {' '.join(args)}\n\n{result.stderr.strip()}")

    return result.stdout


# ==================================================
# VERIFY REPOSITORY
# ==================================================

try:
    run_git(["rev-parse", "--git-dir"])
except RuntimeError as exc:
    print(f"\nERROR: The supplied path is not a valid Git repository.\n{exc}")
    sys.exit(1)


# ==================================================
# CACHE HANDLING
# ==================================================

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {"repository": os.path.abspath(REPO_PATH), "last_commit": None, "co_change": {}}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, json.JSONDecodeError):
        print("\nWARNING: Cache could not be read. Starting a fresh analysis.")
        return {"repository": os.path.abspath(REPO_PATH), "last_commit": None, "co_change": {}}

    cached_repo = os.path.abspath(cache.get("repository", ""))
    current_repo = os.path.abspath(REPO_PATH)

    if cached_repo and cached_repo != current_repo:
        print("\nWARNING: Cache belongs to another repository.\nStarting a fresh analysis.")
        return {"repository": current_repo, "last_commit": None, "co_change": {}}

    return cache


def save_cache(cache):
    temp_file = CACHE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    os.replace(temp_file, CACHE_FILE)


# ==================================================
# GIT HISTORY
# ==================================================

def get_current_head():
    return run_git(["rev-parse", "HEAD"]).strip()


def get_python_commits():
    """
    Return commits (on the current branch only) that touch at
    least one Python file. Deliberately does NOT use --all, so
    only the checked-out branch's history is mined, not every
    branch in the repo (which would include unmerged/abandoned
    branches and skew the co-change signal).
    """
    output = run_git(["log", "--format=%H", "--", "*.py"])
    return [c.strip() for c in output.splitlines() if c.strip()]


def get_commits_to_process(all_commits, last_commit):
    if not last_commit:
        return list(reversed(all_commits))

    if last_commit not in all_commits:
        print("\nWARNING: Cached commit not present in current history (possible force-push/rewrite).")
        print("A full co-change rebuild will be performed.")
        return list(reversed(all_commits))

    index = all_commits.index(last_commit)
    newer_commits = all_commits[:index]
    return list(reversed(newer_commits))


# ==================================================
# DIFF PARSING — always resolves via line -> function
# ==================================================

def get_changed_line_numbers(commit):
    """
    Obtain changed NEW-file line numbers from Git's unified diff.
    This is the ONLY resolution path — we do not trust git's own
    hunk function-context string, since it doesn't include class
    names (e.g. gives 'save' instead of 'User.save'), which would
    silently produce node IDs incompatible with the AST parser's
    output format.
    """
    diff_text = run_git([
        "show", "--format=", "--find-renames", "--find-copies",
        "--unified=0", commit, "--", "*.py"
    ])

    current_file = None
    current_new_line = None
    changed = {}

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip().replace("\\", "/")

        elif line.startswith("+++ /dev/null"):
            current_file = None

        elif line.startswith("@@ "):
            try:
                header = line.split("@@", 2)[1].strip()
                new_part = header.split(" ")[1][1:]  # remove leading '+'
                if "," in new_part:
                    start, _count = new_part.split(",", 1)
                    current_new_line = int(start)
                else:
                    current_new_line = int(new_part)
            except (IndexError, ValueError):
                current_new_line = None

        elif current_file and current_new_line is not None:
            if line.startswith("+") and not line.startswith("+++"):
                changed.setdefault(current_file, set()).add(current_new_line)
                current_new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                continue  # deleted lines don't advance the new-file line counter
            else:
                current_new_line += 1

    return changed


def resolve_changed_lines_to_functions(changed_lines):
    functions = set()
    for path, line_numbers in changed_lines.items():
        prepared_ranges = sorted_function_ranges.get(path, {})
        for line_num in line_numbers:
            func_name = line_to_function(line_num, prepared_ranges)
            functions.add(f"{path}::{func_name}")
    return functions


# ==================================================
# CO-CHANGE COUNTING
# ==================================================

def add_cochange_pairs(co_change, functions_in_commit):
    functions_in_commit = sorted(set(functions_in_commit))

    for function1, function2 in combinations(functions_in_commit, 2):
        co_change.setdefault(function1, {})
        co_change[function1][function2] = co_change[function1].get(function2, 0) + 1

        co_change.setdefault(function2, {})
        co_change[function2][function1] = co_change[function2].get(function1, 0) + 1


# ==================================================
# OUTPUT
# ==================================================

def save_output(co_change):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(co_change, f, indent=2)


# ==================================================
# MAIN
# ==================================================

def main():
    print("\nStarting Git-based co-change analysis...")

    cache = load_cache()
    all_commits = get_python_commits()

    if not all_commits:
        print("\nNo commits containing Python files were found.")
        save_output({})
        return

    current_head = get_current_head()
    last_commit = cache.get("last_commit")
    commits_to_process = get_commits_to_process(all_commits, last_commit)
    co_change = cache.get("co_change", {})

    print(f"\nPython commits in repository: {len(all_commits)}")
    if last_commit:
        print(f"Last processed commit: {last_commit}")
        print(f"New commits to process: {len(commits_to_process)}")
    else:
        print("No previous cache found.")
        print(f"Commits to process: {len(commits_to_process)}")

    if not commits_to_process:
        print("\nNo new commits require processing.")
        save_output(co_change)
        print("\nCo-change analysis is already up to date.")
        print(f"Output saved to: {os.path.abspath(OUTPUT_FILE)}")
        return

    processed = 0
    skipped_mega_commits = 0
    skipped_function_heavy_commits = 0

    for commit in commits_to_process:
        processed += 1
        if processed % 100 == 0 or processed == 1:
            print(f"Processed {processed}/{len(commits_to_process)} commits...")

        changed_lines = get_changed_line_numbers(commit)

        if not changed_lines:
            continue

        python_files = set(changed_lines.keys())

        if len(python_files) > MAX_FILES_PER_COMMIT:
            skipped_mega_commits += 1
            continue

        functions_in_commit = resolve_changed_lines_to_functions(changed_lines)

        if len(functions_in_commit) > MAX_FUNCTIONS_PER_COMMIT:
            skipped_function_heavy_commits += 1
            continue

        if len(functions_in_commit) < 2:
            continue

        add_cochange_pairs(co_change, functions_in_commit)

    cache = {
        "repository": os.path.abspath(REPO_PATH),
        "last_commit": current_head,
        "co_change": co_change
    }
    save_cache(cache)
    save_output(co_change)

    print("\n" + "=" * 60)
    print("Co-change analysis completed.")
    print("=" * 60)
    print("\nOutput saved to:", os.path.abspath(OUTPUT_FILE))
    print("Cache saved to:", os.path.abspath(CACHE_FILE))

    print("\nStatistics:")
    print(f"  Python commits found:         {len(all_commits)}")
    print(f"  Commits processed:            {len(commits_to_process)}")
    print(f"  Mega commits skipped:         {skipped_mega_commits}")
    print(f"  Function-heavy skipped:       {skipped_function_heavy_commits}")
    print(f"  Functions with relationships: {len(co_change)}")

    total_edges = sum(len(rel) for rel in co_change.values()) // 2
    print(f"  Unique co-change edges:       {total_edges}")


if __name__ == "__main__":
    main()
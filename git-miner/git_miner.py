import os
import json
import sys
from itertools import combinations
from pydriller import Repository


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

MAX_FILES_PER_COMMIT = 15


# --------------------------------------------------
# REPOSITORY INPUT
# --------------------------------------------------

if len(sys.argv) < 2:
    print("Usage: python git_miner.py <repository_path_or_url>")
    sys.exit(1)

REPO_PATH = sys.argv[1]


# --------------------------------------------------
# LOAD AST FUNCTION INFORMATION
# --------------------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

AST_FILE = os.path.join(
    PROJECT_ROOT,
    "ast-parser",
    "output",
    "ast_dependencies.json"
)


if not os.path.exists(AST_FILE):
    print("\nERROR: AST output file not found.")
    print("Expected file:")
    print(AST_FILE)
    print("\nAsk the AST Parser member for:")
    print("ast-parser/output/ast_dependencies.json")
    sys.exit(1)


with open(AST_FILE, "r", encoding="utf-8") as f:
    ast_data = json.load(f)


# --------------------------------------------------
# BUILD FILE -> FUNCTION ID MAPPING
# --------------------------------------------------

file_functions = {}

for function_id in ast_data.keys():

    file_path = function_id.split("::")[0]

    file_functions.setdefault(
        file_path,
        []
    ).append(function_id)


# --------------------------------------------------
# CO-CHANGE ANALYSIS
# --------------------------------------------------

co_change = {}


for commit in Repository(REPO_PATH).traverse_commits():

    modified_files = commit.modified_files

    # Ignore mega commits
    if len(modified_files) > MAX_FILES_PER_COMMIT:
        continue

    python_files = []

    for modified_file in modified_files:

        # For renamed/deleted files, use whichever path exists
        path = (
            modified_file.new_path
            or modified_file.old_path
        )

        if path and path.endswith(".py"):
            python_files.append(path)

    # Remove duplicate file paths
    python_files = sorted(set(python_files))


    # --------------------------------------------------
    # CONVERT FILES TO FUNCTION IDs
    # --------------------------------------------------

    functions_in_commit = []

    for file_path in python_files:

        functions = file_functions.get(
            file_path,
            []
        )

        functions_in_commit.extend(functions)


    # Remove duplicate function IDs
    functions_in_commit = sorted(
        set(functions_in_commit)
    )


    # --------------------------------------------------
    # COUNT FUNCTION CO-CHANGES
    # --------------------------------------------------

    for function1, function2 in combinations(
        functions_in_commit,
        2
    ):

        # function1 -> function2
        co_change.setdefault(
            function1,
            {}
        )

        co_change[function1][function2] = (
            co_change[function1].get(function2, 0)
            + 1
        )

        # function2 -> function1
        co_change.setdefault(
            function2,
            {}
        )

        co_change[function2][function1] = (
            co_change[function2].get(function1, 0)
            + 1
        )


# --------------------------------------------------
# CREATE OUTPUT DIRECTORY
# --------------------------------------------------

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "output"
)

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


# --------------------------------------------------
# SAVE OUTPUT
# --------------------------------------------------

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "cochange.json"
)


with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        co_change,
        f,
        indent=2
    )


# --------------------------------------------------
# DISPLAY RESULT
# --------------------------------------------------

print("\nCo-change analysis completed.")

print("\nOutput saved to:")
print(os.path.abspath(OUTPUT_FILE))

print("\nFunction co-change frequencies:")

for function1, relationships in co_change.items():

    for function2, frequency in relationships.items():

        print(
            function1,
            "<->",
            function2,
            "=",
            frequency
        )
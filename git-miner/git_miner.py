import os
import json
from itertools import combinations
from pydriller import Repository


# Repository to analyze
REPO_PATH = "../../test_repo"

# Ignore very large commits
MAX_FILES_PER_COMMIT = 10

# Store co-change frequencies
co_change = {}


# Traverse all commits
for commit in Repository(REPO_PATH).traverse_commits():

    modified_files = commit.modified_files

    # Skip very large commits
    if len(modified_files) > MAX_FILES_PER_COMMIT:
        continue

    # Keep only Python files
    python_files = []

    for modified_file in modified_files:

        # Use new path if available,
        # otherwise use old path
        path = modified_file.new_path or modified_file.old_path

        if path and path.endswith(".py"):
            python_files.append(path)

    # Remove duplicate files
    python_files = sorted(set(python_files))

    # Generate every possible pair
    for file1, file2 in combinations(python_files, 2):

        pair = (file1, file2)

        co_change[pair] = co_change.get(pair, 0) + 1


# Convert dictionary into a JSON-friendly structure
co_change_output = []

for (file1, file2), frequency in co_change.items():

    co_change_output.append({
        "file1": file1,
        "file2": file2,
        "frequency": frequency
    })


# Save JSON
output_file = "co_change.json"

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(co_change_output, f, indent=4)


# Print results
print("\nCo-change analysis completed.")

print(
    "Output saved to:",
    os.path.abspath(output_file)
)

print("\nCo-change frequencies:")

for item in co_change_output:

    print(
        item["file1"],
        "<->",
        item["file2"],
        "=",
        item["frequency"]
    )
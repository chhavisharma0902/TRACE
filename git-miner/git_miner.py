import os
import json
import sys
from itertools import combinations
from pydriller import Repository

MAX_FILES_PER_COMMIT = 10

if len(sys.argv) < 2:
    print("Usage: python git_miner.py <repository_path_or_url>")
    sys.exit(1)

REPO_PATH = sys.argv[1]

co_change = {}

for commit in Repository(REPO_PATH).traverse_commits():

    modified_files = commit.modified_files

    if len(modified_files) > MAX_FILES_PER_COMMIT:
        continue

    python_files = []

    for modified_file in modified_files:

        path = modified_file.new_path or modified_file.old_path

        if path and path.endswith(".py"):
            python_files.append(path)

    python_files = sorted(set(python_files))

    for file1, file2 in combinations(python_files, 2):

        key = (file1, file2)

        co_change[key] = co_change.get(key, 0) + 1


output_file = "co_change.json"

data = []

for (file1, file2), frequency in co_change.items():

    data.append({
        "file1": file1,
        "file2": file2,
        "frequency": frequency
    })


with open(output_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)


print("\nCo-change analysis completed.")
print("Output saved to:", os.path.abspath(output_file))

print("\nCo-change frequencies:")

for item in data:
    print(
        item["file1"],
        "<->",
        item["file2"],
        "=",
        item["frequency"]
    )
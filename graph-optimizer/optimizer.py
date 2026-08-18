import json
import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CO_CHANGE_FILE = os.path.join(
    BASE_DIR,
    "git-miner",
    "co_change.json"
)

OUTPUT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "weights.json"
)


# Load co-change data
with open(CO_CHANGE_FILE, "r", encoding="utf-8") as f:
    co_change_data = json.load(f)


# Calculate weights
weights = []

for item in co_change_data:
    file1 = item["file1"]
    file2 = item["file2"]
    frequency = item["frequency"]

    # Simple normalized relationship weight
    weight = frequency

    weights.append({
        "file1": file1,
        "file2": file2,
        "frequency": frequency,
        "weight": weight
    })


# Save weights
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(weights, f, indent=4)


# Display results
print("\nGraph optimization completed.")
print("Output saved to:", OUTPUT_FILE)

print("\nFile relationship weights:")

for item in weights:
    print(
        item["file1"],
        "<->",
        item["file2"],
        "=",
        item["weight"]
    )
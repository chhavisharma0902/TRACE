import json
from pathlib import Path

import networkx as nx

g = nx.MultiGraph()
g.add_edge("src/auth.py", "src/models.py", kind="ast", weight=1)
g.add_edge("src/auth.py", "src/models.py", kind="git", weight=8)
g.add_edge("src/auth.py", "src/utils.py", kind="git", weight=2)
g.add_edge("src/models.py", "src/db.py", kind="ast", weight=1)

out_dir = Path("graph_data")
out_dir.mkdir(exist_ok=True)

nx.write_graphml(g, out_dir / "graph.graphml")
(out_dir / "weights.json").write_text(json.dumps({"w_ast": 0.5, "w_git": 0.5}))

print("Wrote graph_data/graph.graphml and graph_data/weights.json")
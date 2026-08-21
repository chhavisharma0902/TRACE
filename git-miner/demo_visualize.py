import json
import networkx as nx
from pyvis.network import Network

# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

MIN_COCHANGE_WEIGHT = 3   # only show relationships that co-changed at least this many times
MAX_NODES = 80            # cap the graph to the top N most-connected nodes

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

with open("output/cochange.json") as f:
    cochange_data = json.load(f)

print(f"Loaded {len(cochange_data)} function entries")

# --------------------------------------------------
# BUILD GRAPH
# --------------------------------------------------

G = nx.MultiDiGraph()

for source, targets in cochange_data.items():
    for target, count in targets.items():
        if count < MIN_COCHANGE_WEIGHT:
            continue
        G.add_node(source)
        G.add_node(target)
        G.add_edge(source, target, weight=count, edge_type="cochange")

print(f"After weight filter -> Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

# Cap to most-connected nodes if still too large
if G.number_of_nodes() > MAX_NODES:
    degrees = dict(G.degree())
    top_nodes = sorted(degrees, key=degrees.get, reverse=True)[:MAX_NODES]
    G = G.subgraph(top_nodes).copy()

print(f"Final -> Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

# --------------------------------------------------
# BUILD VISUALIZATION
# --------------------------------------------------

net = Network(
    notebook=False,
    directed=True,
    height="750px",
    width="100%",
    bgcolor="#1e1e1e",
    font_color="white"
)

net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=200)
net.from_nx(G)
net.toggle_physics(False)   # disable continuous physics recalculation for performance

for node in net.nodes:
    node["color"] = "#FFB74D"
    node["size"] = 12
    node["label"] = node["id"].split("/")[-1]
    node["title"] = node["id"]

for edge in net.edges:
    edge["color"] = "#E57373"
    edge["arrows"] = "to"
    edge["title"] = f"co-changed {edge.get('weight', 1)} times"
    edge["width"] = 0.5

net.write_html("cochange_graph.html", open_browser=False, notebook=False)
print("Saved visualization to cochange_graph.html")
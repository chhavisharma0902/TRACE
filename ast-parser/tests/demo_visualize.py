import json
import networkx as nx
from pyvis.network import Network

# Load the AST parser's own output
with open("output/ast_dependencies.json") as f:
    ast_data = json.load(f)

print(f"Loaded {len(ast_data)} function entries")

# Build the graph
G = nx.MultiDiGraph()

for source, targets in ast_data.items():
    G.add_node(source)
    for target in targets:
        G.add_node(target)
        G.add_edge(source, target, edge_type="call")

print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

# Build PyVis visualization
net = Network(
    notebook=False,
    directed=True,
    height="750px",
    width="100%",
    bgcolor="#1e1e1e",
    font_color="white"
)

net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=150)
net.from_nx(G)

for node in net.nodes:
    node["color"] = "#4FC3F7"
    node["size"] = 12
    node["label"] = node["id"].split("/")[-1]
    node["title"] = node["id"]

for edge in net.edges:
    edge["color"] = "#81C784"
    edge["arrows"] = "to"

net.write_html("ast_dependency_graph.html", open_browser=False, notebook=False)
print("Saved visualization to ast_dependency_graph.html")
import sys
sys.path.insert(0, "src")
from recommend import RecommendationEngine

engine = RecommendationEngine(
    graph_file="../multigraph-builder/output/unified_graph.json",
    weights_file="output/best_weights.json",
)

# pick a real function name from your unified_graph.json
print(engine.get_recommendations("src/flask/app.py::Flask.run", k=5))
print(engine.get_ego_graph_data("src/flask/app.py::Flask.run", radius=1))
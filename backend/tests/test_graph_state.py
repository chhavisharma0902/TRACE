# backend/tests/test_graph_state.py
from src.graph_state import GraphState

def test_scoring_with_hand_built_graph():
    gs = GraphState()
    gs.w_ast, gs.w_git = 0.5, 0.5
    gs.graph.add_edge("src/auth.py", "src/models.py", kind="ast", weight=1)
    gs.graph.add_edge("src/auth.py", "src/models.py", kind="git", weight=8)
    gs.graph.add_edge("src/auth.py", "src/utils.py", kind="git", weight=2)
    gs._max_git_count = 8

    results = gs.get_recommendations("src/auth.py")
    assert results[0]["file_path"] == "src/models.py"  # has both ast+git — should rank first
    assert results[0]["score"] == 1.0                   # 0.5*1 + 0.5*(8/8)

def test_isolated_file_returns_empty():
    gs = GraphState()
    assert gs.get_recommendations("src/new_file.py") == []
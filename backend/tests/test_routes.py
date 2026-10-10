import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.graph_state import graph_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_graph():
    """Runs before every test in this file — gives each test a clean, known graph."""
    graph_state.graph.clear()
    graph_state.graph.add_edge("src/auth.py", "src/models.py", kind="ast", weight=1)
    graph_state.graph.add_edge("src/auth.py", "src/models.py", kind="git", weight=8)
    graph_state.graph.add_edge("src/auth.py", "src/utils.py", kind="git", weight=2)
    graph_state._max_git_count = 8
    graph_state.w_ast, graph_state.w_git = 0.5, 0.5


def test_health_check_reports_node_count():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["nodes_loaded"] == 3


def test_recommend_ranks_highest_combined_score_first():
    response = client.get("/api/recommend", params={"file_path": "src/auth.py"})
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"][0]["file_path"] == "src/models.py"
    assert body["recommendations"][0]["score"] == 1.0


def test_recommend_unknown_file_returns_empty_list():
    response = client.get("/api/recommend", params={"file_path": "src/does_not_exist.py"})
    assert response.status_code == 200
    assert response.json()["recommendations"] == []


def test_recommend_windows_backslash_path_still_matches():
    # Member 5's OS-slash edge case — Windows sends \, graph is stored with /
    response = client.get("/api/recommend", params={"file_path": "src\\auth.py"})
    assert response.status_code == 200
    assert response.json()["recommendations"][0]["file_path"] == "src/models.py"


def test_update_file_replaces_ast_edges_only():
    response = client.post("/api/update-file", json={
        "file_path": "src/auth.py",
        "source_code": "import os\nfrom src.db import connect\n",
    })
    assert response.status_code == 200
    assert response.json()["ast_edges_updated"] == 2

    # git edge to utils.py must survive an AST-only update
    updated = graph_state.get_recommendations("src/auth.py")
    files = [r["file_path"] for r in updated]
    assert "src/utils.py" in files
    assert "src/db.py" in files  # new AST edge from the update


def test_update_file_with_syntax_error_does_not_crash():
    response = client.post("/api/update-file", json={
        "file_path": "src/broken.py",
        "source_code": "def broken(:",
    })
    assert response.status_code == 200
    assert response.json()["ast_edges_updated"] == 0
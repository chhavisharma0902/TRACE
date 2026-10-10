import json

import pytest
from fastapi.testclient import TestClient

from src import config, llm_client
from src.engine_state import engine_state
from src.function_resolver import FunctionResolver
from src.main import app

client = TestClient(app)  # no `with`: lifespan is skipped, state is injected below


class FakeEngine:
    G = None

    def node_count(self):
        return 3

    def get_recommendations(self, function_id, k=5, reference_date=None):
        if function_id != "src/auth.py::login":
            return []
        recs = [
            {"function_id": "src/models.py::User", "score": 0.9, "via_call": True, "via_cochange": True},
            {"function_id": "src/utils.py::hash", "score": 0.4, "via_call": False, "via_cochange": True},
        ]
        return recs[:k]

    def get_ego_graph_data(self, function_id, radius=2, reference_date=None):
        if function_id != "src/auth.py::login":
            return {"nodes": [], "edges": []}  # real engine omits "center" here
        return {
            "center": function_id,
            "nodes": [function_id, "src/models.py::User"],
            "edges": [{"source": function_id, "target": "src/models.py::User", "edge_type": "call", "count": None}],
        }


@pytest.fixture(autouse=True)
def injected_state(tmp_path):
    ranges = tmp_path / "ranges.json"
    ranges.write_text(json.dumps({"src/auth.py": {"login": [10, 30]}}), encoding="utf-8")

    saved = (engine_state.engine, engine_state.resolver, engine_state.mode, engine_state.error)
    engine_state.engine = FakeEngine()
    engine_state.resolver = FunctionResolver(ranges)
    engine_state.mode, engine_state.error = "real", None
    yield
    engine_state.engine, engine_state.resolver, engine_state.mode, engine_state.error = saved


# ---------- health ----------
def test_health_reports_mode_and_nodes():
    body = client.get("/").json()
    assert body["status"] == "ok" and body["mode"] == "real" and body["nodes"] == 3


# ---------- /api/recommend ----------
def test_recommend_by_function_id():
    r = client.get("/api/recommend", params={"function_id": "src/auth.py::login"})
    assert r.status_code == 200
    body = r.json()
    assert body["function_id"] == "src/auth.py::login"
    assert body["recommendations"][0]["function_id"] == "src/models.py::User"


def test_recommend_by_file_and_line():
    r = client.get("/api/recommend", params={"file_path": "src/auth.py", "line": 15})
    assert r.json()["function_id"] == "src/auth.py::login"
    assert len(r.json()["recommendations"]) == 2


def test_recommend_windows_path_in_function_id_is_normalized():
    r = client.get("/api/recommend", params={"function_id": "src\\auth.py::login"})
    assert r.json()["recommendations"]


def test_recommend_unknown_function_returns_empty_list():
    r = client.get("/api/recommend", params={"function_id": "src/nope.py::x"})
    assert r.status_code == 200 and r.json()["recommendations"] == []


def test_recommend_line_outside_any_function_returns_empty_list():
    r = client.get("/api/recommend", params={"file_path": "src/auth.py", "line": 1})
    assert r.status_code == 200
    assert r.json() == {"function_id": None, "recommendations": []}


def test_recommend_respects_k():
    r = client.get("/api/recommend", params={"function_id": "src/auth.py::login", "k": 1})
    assert len(r.json()["recommendations"]) == 1


def test_recommend_without_target_is_400():
    assert client.get("/api/recommend").status_code == 400
    assert client.get("/api/recommend", params={"file_path": "src/auth.py"}).status_code == 400


def test_recommend_line_zero_is_rejected():
    r = client.get("/api/recommend", params={"file_path": "src/auth.py", "line": 0})
    assert r.status_code == 422


def test_recommend_503_when_engine_not_loaded():
    engine_state.engine = None
    engine_state.error = "missing file(s): x"
    r = client.get("/api/recommend", params={"function_id": "src/auth.py::login"})
    assert r.status_code == 503 and "missing file" in r.json()["detail"]


def test_recommend_file_line_503_when_resolver_missing():
    engine_state.resolver = None
    r = client.get("/api/recommend", params={"file_path": "src/auth.py", "line": 15})
    assert r.status_code == 503


# ---------- /api/ego-graph ----------
def test_ego_graph_returns_nodes_and_edges():
    r = client.get("/api/ego-graph", params={"function_id": "src/auth.py::login", "radius": 1})
    body = r.json()
    assert body["center"] == "src/auth.py::login"
    assert len(body["nodes"]) == 2 and body["edges"][0]["edge_type"] == "call"


def test_ego_graph_unknown_function_still_has_center_key():
    r = client.get("/api/ego-graph", params={"function_id": "src/nope.py::x"})
    assert r.status_code == 200
    assert r.json() == {"center": "src/nope.py::x", "nodes": [], "edges": []}


def test_ego_graph_by_file_and_line():
    r = client.get("/api/ego-graph", params={"file_path": "src/auth.py", "line": 20})
    assert r.json()["center"] == "src/auth.py::login"


def test_ego_graph_radius_is_capped():
    r = client.get("/api/ego-graph", params={"function_id": "src/auth.py::login", "radius": 9})
    assert r.status_code == 422


# ---------- /api/suggest-fix ----------
@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "limiter", llm_client.RateLimiter(10, 100))
    calls = []

    def fake_generate(prompt):
        calls.append(prompt)
        return "Update the call site.\n```diff\n- a\n+ b\n```"

    monkeypatch.setattr(llm_client, "generate_suggestion", fake_generate)
    return calls


BODY = {"function_id": "src/auth.py::login", "diff": "- old\n+ new", "function_source": "def login(): ..."}


def test_suggest_fix_returns_text_and_never_auto_applies(llm):
    r = client.post("/api/suggest-fix", json=BODY)
    assert r.status_code == 200
    body = r.json()
    assert body["auto_apply"] is False
    assert "diff" in body["suggestion"]
    assert body["related_functions"] == ["src/models.py::User", "src/utils.py::hash"]
    assert "src/models.py::User" in llm[0] and "- old" in llm[0]  # engine context + diff reach the prompt


def test_suggest_fix_503_without_api_key(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert client.post("/api/suggest-fix", json=BODY).status_code == 503


def test_suggest_fix_rate_limited_per_function(llm):
    assert client.post("/api/suggest-fix", json=BODY).status_code == 200
    second = client.post("/api/suggest-fix", json=BODY)
    assert second.status_code == 429 and "retry-after" in second.headers
    assert len(llm) == 1  # the blocked call never reached the LLM


def test_suggest_fix_llm_failure_is_502(llm, monkeypatch):
    def boom(prompt):
        raise llm_client.LLMCallFailed("quota exceeded")

    monkeypatch.setattr(llm_client, "generate_suggestion", boom)
    r = client.post("/api/suggest-fix", json=BODY)
    assert r.status_code == 502 and "quota" not in r.json()["detail"]


def test_suggest_fix_works_even_if_engine_is_down(llm):
    engine_state.engine = None
    r = client.post("/api/suggest-fix", json=BODY)
    assert r.status_code == 200 and r.json()["related_functions"] == []


def test_suggest_fix_validates_body(llm):
    assert client.post("/api/suggest-fix", json={"function_id": "src/a.py::f"}).status_code == 422


# ---------- rate limiter unit tests ----------
def test_limiter_per_key_cooldown_and_global_cap():
    now = [0.0]
    lim = llm_client.RateLimiter(10, 2, clock=lambda: now[0])
    assert lim.acquire("a") == 0
    assert lim.acquire("a") == pytest.approx(10)   # same function too soon
    assert lim.acquire("b") == 0                    # different function is fine
    assert lim.acquire("c") > 0                     # global cap of 2/minute reached
    now[0] = 61
    assert lim.acquire("c") == 0                    # window has passed

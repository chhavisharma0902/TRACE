import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from src.graph_state import graph_state

router = APIRouter()

MOCK_DATA_PATH = Path(__file__).resolve().parents[2] / "mock_data" / "mock_recommendations.json"

with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
    _mock_data = json.load(f)


@router.get("/api/recommend")
def get_recommendations(file_path: str, top_n: int = 5):
    recommendations = graph_state.get_recommendations(file_path, top_n=top_n)
    return {"file_path": file_path, "recommendations": recommendations}
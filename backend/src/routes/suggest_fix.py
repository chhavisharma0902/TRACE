import logging
import math
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src import config, llm_client
from src.engine_state import engine_state
from src.routes.common import normalize_function_id

logger = logging.getLogger("trace.suggest_fix")
router = APIRouter()


class SuggestFixRequest(BaseModel):
    function_id: str = Field(min_length=3, description="The flagged function, e.g. src/app.py::Flask.run")
    diff: str = Field(min_length=1, max_length=200_000, description="The developer's edit, as a diff")
    function_source: Optional[str] = Field(
        None, max_length=200_000, description="Current source of the flagged function (strongly recommended)"
    )


@router.post("/api/suggest-fix")
def suggest_fix(req: SuggestFixRequest):
    function_id = normalize_function_id(req.function_id)

    if not llm_client.is_configured():
        raise HTTPException(status_code=503, detail="LLM not configured: set GEMINI_API_KEY in backend/.env")

    wait = llm_client.limiter.acquire(function_id)
    if wait > 0:
        retry_after = math.ceil(wait)
        raise HTTPException(
            status_code=429,
            detail=f"Too many suggestion requests. Retry in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    related: list[str] = []
    if engine_state.engine is not None:
        related = [r["function_id"] for r in engine_state.engine.get_recommendations(function_id, k=5)]

    prompt = llm_client.build_prompt(function_id, req.diff, req.function_source, related)
    try:
        suggestion = llm_client.generate_suggestion(prompt)
    except llm_client.LLMCallFailed as exc:
        logger.warning("LLM call failed for %s: %s", function_id, exc)
        raise HTTPException(status_code=502, detail="The LLM request failed. Try again shortly.")

    return {
        "function_id": function_id,
        "suggestion": suggestion,
        "auto_apply": False,  # contract: the extension must only DISPLAY this
        "model": config.GEMINI_MODEL,
        "related_functions": related,
    }

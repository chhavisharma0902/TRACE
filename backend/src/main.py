from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import llm_client
from src.engine_state import engine_state
from src.routes import ego_graph, recommend, suggest_fix


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the engine ONCE at startup, never per request.
    engine_state.load()
    info = engine_state.describe()
    if info["mode"] == "unavailable":
        print(f"WARNING: engine not loaded: {info['error']}")
    else:
        print(f"Engine loaded ({info['mode']} mode), nodes: {info['nodes']}")
    if not info["resolver_loaded"]:
        print(f"WARNING: file+line lookup disabled: {info['resolver_error']}")
    yield


app = FastAPI(title="TRACE Backend", lifespan=lifespan)

# No cookies are used, so credentials stay off; that also keeps "*" origins valid.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommend.router)
app.include_router(ego_graph.router)
app.include_router(suggest_fix.router)


@app.get("/")
def health_check():
    info = engine_state.describe()
    info["status"] = "ok" if info["mode"] != "unavailable" else "degraded"
    info["llm_configured"] = llm_client.is_configured()
    return info

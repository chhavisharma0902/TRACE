from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.routes import recommend, update_file
from src.graph_state import graph_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    if GRAPH_PATH.exists():
        graph_state.load_from_graphml(GRAPH_PATH, WEIGHTS_PATH)
        print(f"Loaded graph: {graph_state.graph.number_of_nodes()} nodes")
    else:
        print(f"WARNING: no graph found at {GRAPH_PATH} — serving empty graph")

    yield
    # --- shutdown (nothing needed yet)


app = FastAPI(title="Code Recommendation Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommend.router)
app.include_router(update_file.router)

GRAPH_PATH = Path(__file__).resolve().parents[1] / "graph_data" / "graph.graphml"
WEIGHTS_PATH = Path(__file__).resolve().parents[1] / "graph_data" / "weights.json"


@app.get("/")
def health_check():
    return {"status": "ok", "nodes_loaded": graph_state.graph.number_of_nodes()}
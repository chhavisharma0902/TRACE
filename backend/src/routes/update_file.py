import ast

from fastapi import APIRouter
from pydantic import BaseModel

from src.graph_state import graph_state

router = APIRouter()


class UpdateFileRequest(BaseModel):
    file_path: str
    source_code: str


class ImportVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name.replace(".", "/") + ".py")

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            self.imports.append(node.module.replace(".", "/") + ".py")


def extract_imports(source_code: str) -> list[str]:
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        # doc's edge case: a file mid-edit can have unclosed brackets etc.
        # Don't crash the request — just skip updating this file's edges.
        return []
    visitor = ImportVisitor()
    visitor.visit(tree)
    return visitor.imports


@router.post("/api/update-file")
async def update_file(request: UpdateFileRequest):
    imports = extract_imports(request.source_code)
    graph_state.update_file_ast_edges(request.file_path, imports)
    return {"status": "ok", "file_path": request.file_path, "ast_edges_updated": len(imports)}
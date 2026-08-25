from fastapi import FastAPI, HTTPException
from investigation_world.core.models import CanonicalWorld, InvestigationBudget, InvestigationResult
from investigation_world.search.index import FrozenSearchIndex
import json
from pathlib import Path
app = FastAPI(title="Investigation World")
current_world: CanonicalWorld | None = None
search_index: FrozenSearchIndex | None = None
@app.post("/load")
def load_world(world_path: str):
    global current_world, search_index
    current_world = CanonicalWorld.model_validate_json(Path(world_path).read_text())
    search_index = FrozenSearchIndex()
    search_index.build(current_world)
    return {"world_id": current_world.world_id, "entities": len(current_world.people) + len(current_world.organizations)}
@app.post("/search/web")
def web_search(query: str, limit: int = 10):
    if not current_world or not search_index: raise HTTPException(status_code=400, detail="no world loaded")
    return search_index.search(query, limit)
@app.get("/documents/{doc_id}")
def get_document(doc_id: str):
    if not current_world: raise HTTPException(status_code=400, detail="no world loaded")
    doc = next((d for d in current_world.documents if d.document_id == doc_id), None)
    if not doc: raise HTTPException(status_code=404, detail="document not found")
    return {"document_id": doc.document_id, "title": doc.title, "body": doc.body, "published_at": doc.published_at, "source_type": next((s.source_type for s in current_world.sources if s.source_id == doc.source_id), "unknown")}
@app.get("/budget")
def get_budget():
    return {"total_cost": 40, "max_tool_calls": 30}
@app.post("/verify")
def verify_submission(result: InvestigationResult):
    from investigation_world.verifier.aggregate import verify
    if not current_world: raise HTTPException(status_code=400, detail="no world loaded")
    return verify(result, current_world, task_answerable=True)
"}},{

from fastapi import FastAPI,HTTPException
from pathlib import Path
from investigation_world.core.models import CanonicalWorld,InvestigationResult
from investigation_world.search.index import FrozenSearchIndex
from investigation_world.tools.budget import BudgetManager
app=FastAPI(title='Investigation World',version='0.2.0'); current_world=None; search_index=None; manager=BudgetManager()
def charge(name):
 try: manager.charge(name)
 except ValueError as e: raise HTTPException(429,str(e))
@app.post('/load')
def load_world(world_path:str):
 global current_world,search_index
 current_world=CanonicalWorld.model_validate_json(Path(world_path).read_text()); search_index=FrozenSearchIndex(); search_index.build(current_world); return {'world_id':current_world.world_id,'documents':len(current_world.documents)}
@app.post('/search/web')
def web_search(query:str,limit:int=10):
 charge('web_search'); return search_index.search(query,limit) if search_index else []
@app.post('/search/documents')
def document_search(query:str,limit:int=10):
 charge('document_search'); return search_index.search(query,limit) if search_index else []
@app.post('/registry/search')
def registry_search(query:str,limit:int=10):
 charge('registry_search'); return search_index.search(query,limit) if search_index else []
@app.get('/documents/{doc_id}')
def get_document(doc_id:str):
 charge('open_page')
 if current_world is None: raise HTTPException(400,'no world loaded')
 d=next((x for x in current_world.documents if x.document_id==doc_id),None)
 if d is None: raise HTTPException(404,'document not found')
 return {'document_id':d.document_id,'title':d.title,'body':d.body,'published_at':d.published_at,'cites_document_ids':d.cites_document_ids}
@app.get('/budget')
def get_budget(): return manager.snapshot()
@app.post('/submit')
def submit(result:InvestigationResult):
 if current_world is None: raise HTTPException(400,'no world loaded')
 from investigation_world.verifier.aggregate import verify
 return verify(result,current_world,budget_spent=manager.budget.spent,budget_total=manager.budget.total_cost)

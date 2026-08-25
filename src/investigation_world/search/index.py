import sqlite3
from investigation_world.core.models import CanonicalWorld
class FrozenSearchIndex:
 def __init__(self,path=':memory:'):
  self.db=sqlite3.connect(path); self.db.row_factory=sqlite3.Row; self.db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(document_id UNINDEXED,title,body)')
 def build(self,world:CanonicalWorld):
  self.db.execute('DELETE FROM documents'); self.db.executemany('INSERT INTO documents(document_id,title,body) VALUES (?,?,?)',[(d.document_id,d.title,d.body) for d in world.documents]); self.db.commit()
 def search(self,query:str,limit:int=10):
  if not query.strip(): return []
  safe=' '.join('"'+part.replace('"','')+'"' for part in query.split())
  return [dict(r) for r in self.db.execute('SELECT document_id,title,body FROM documents WHERE documents MATCH ? LIMIT ?',(safe,max(1,min(limit,100))))]

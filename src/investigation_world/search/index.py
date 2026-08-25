import sqlite3
from investigation_world.core.models import CanonicalWorld
class FrozenSearchIndex:
    def __init__(self,path=':memory:'):
        self.db=sqlite3.connect(path); self.db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(document_id,title,body)')
    def build(self,world:CanonicalWorld):
        self.db.execute('DELETE FROM documents'); self.db.executemany('INSERT INTO documents VALUES (?,?,?)',[(d.document_id,d.title,d.body) for d in world.documents]); self.db.commit()
    def search(self,query,limit=10): return [{'document_id':r[0],'title':r[1],'body':r[2]} for r in self.db.execute('SELECT document_id,title,body FROM documents WHERE documents MATCH ? LIMIT ?',(query,limit))]


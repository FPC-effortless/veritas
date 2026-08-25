from collections import defaultdict, deque
class ProvenanceDAG:
    def __init__(self): self.parents:dict[str,set[str]]=defaultdict(set)
    def add_citation(self, child:str, parent:str):
        if child==parent or self._reachable(parent,child): raise ValueError("provenance cycle")
        self.parents[child].add(parent)
    def _reachable(self,start,target):
        todo=[start]; seen=set()
        while todo:
            n=todo.pop()
            if n==target:return True
            if n in seen:continue
            seen.add(n); todo.extend(self.parents.get(n,()))
        return False
    def get_provenance_ancestors(self,doc_id):
        out=set(); todo=list(self.parents.get(doc_id,()))
        while todo:
            n=todo.pop()
            if n in out:continue
            out.add(n); todo.extend(self.parents.get(n,()))
        return out
    def get_root_sources(self,doc_ids):
        roots=set()
        for d in doc_ids:
            anc=self.get_provenance_ancestors(d)|{d}; roots|={x for x in anc if not self.parents.get(x)}
        return roots
    def independent_source_count(self,doc_ids): return len(self.get_root_sources(doc_ids))


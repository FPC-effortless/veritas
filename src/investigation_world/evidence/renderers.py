from investigation_world.core.models import *

def render_document(doc:Document, source:Source)->str:
    prefix={SourceType.REGISTRY:'REGISTRY RECORD',SourceType.COMPANY_SITE:'ABOUT / LEADERSHIP',SourceType.NEWS:'NEWS REPORT',SourceType.FILING:'STATUTORY FILING',SourceType.ARCHIVE:'ARCHIVED SNAPSHOT',SourceType.DIRECTORY:'BUSINESS DIRECTORY'}[source.source_type]
    return f'{prefix}\nTitle: {doc.title}\nPublished: {doc.published_at.isoformat()}\n\n{doc.body}'

def render_all(world:CanonicalWorld):
    sources={s.source_id:s for s in world.sources}
    return {d.document_id:render_document(d,sources[d.source_id]) for d in world.documents if d.source_id in sources}

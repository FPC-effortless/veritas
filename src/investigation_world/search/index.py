from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from investigation_world.core.models import CanonicalWorld, SourceType


class FrozenSearchIndex:
    COLUMNS = ["document_id", "source_type", "published_at", "title", "body"]

    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        existing = [row[1] for row in self.db.execute("PRAGMA table_info(documents)")]
        if existing and existing != self.COLUMNS:
            self.db.execute("DROP TABLE documents")
        self.db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5("
            "document_id UNINDEXED, source_type UNINDEXED, published_at UNINDEXED, title, body)"
        )

    def build(self, world: CanonicalWorld) -> None:
        source_types = {source.source_id: source.source_type.value for source in world.sources}
        self.db.execute("DELETE FROM documents")
        self.db.executemany(
            "INSERT INTO documents(document_id, source_type, published_at, title, body) VALUES (?,?,?,?,?)",
            [
                (
                    document.document_id,
                    source_types.get(document.source_id, SourceType.DIRECTORY.value),
                    document.published_at.isoformat(),
                    document.title,
                    document.body,
                )
                for document in world.documents
            ],
        )
        self.db.commit()

    def search(
        self,
        query: str,
        limit: int = 10,
        source_types: Iterable[SourceType | str] | None = None,
    ) -> list[dict]:
        if not query.strip():
            return []
        safe_query = " ".join('"' + part.replace('"', "") + '"' for part in query.split())
        bounded_limit = max(1, min(limit, 100))
        filters = [
            source_type.value if isinstance(source_type, SourceType) else str(source_type)
            for source_type in (source_types or [])
        ]
        if filters:
            placeholders = ",".join("?" for _ in filters)
            sql = (
                "SELECT document_id, source_type, published_at, title, body "
                "FROM documents WHERE documents MATCH ? "
                f"AND source_type IN ({placeholders}) LIMIT ?"
            )
            params = [safe_query, *filters, bounded_limit]
        else:
            sql = (
                "SELECT document_id, source_type, published_at, title, body "
                "FROM documents WHERE documents MATCH ? LIMIT ?"
            )
            params = [safe_query, bounded_limit]
        return [dict(row) for row in self.db.execute(sql, params)]

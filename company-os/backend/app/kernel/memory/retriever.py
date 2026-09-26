"""
app/kernel/memory/retriever.py
──────────────────────────────
Retrieval behind one interface. Today: Postgres full-text search (ranked,
heading-weighted, OR-matched so natural-language questions work). Vector or
hybrid retrieval can be added as another `Retriever` once an embedding provider
is chosen (plan Review, correction 3) — callers and evals don't change.

Every hit is a citation: document, chunk, heading path and a highlighted
snippet. Nothing is returned that can't be pointed at.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Citation:
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    heading: str
    snippet: str
    content: str
    score: float

    def as_dict(self, with_content: bool = False) -> dict:
        d = asdict(self)
        if not with_content:
            d.pop("content")
        return d


class Retriever(Protocol):
    def search(self, db: Session, workspace_id: int, query: str, limit: int = 5) -> list[Citation]: ...


# The query's own lexemes (stemmed, stop-words removed by the 'english' config)
# OR-ed together, each quoted so punctuation in a lexeme can't break the query
# syntax. 'simple' config on the second pass: the lexemes are already stemmed.
_SQL = text(
    """
    WITH q AS (
      SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | ')) AS query
      FROM unnest(tsvector_to_array(to_tsvector('english', :query))) AS lexeme
    )
    SELECT c.id, c.document_id, c.chunk_index, c.heading, c.content, d.title,
           ts_rank_cd(c.tsv, q.query, 32) AS score,
           ts_headline('english', c.content, q.query,
                       'MaxFragments=2, MinWords=8, MaxWords=30, StartSel=«, StopSel=»') AS snippet
    FROM document_chunks c
    JOIN documents d ON d.id = c.document_id AND d.workspace_id = c.workspace_id
    CROSS JOIN q
    WHERE c.workspace_id = :workspace_id
      AND q.query IS NOT NULL
      AND c.tsv @@ q.query
    ORDER BY score DESC, c.id
    LIMIT :limit
    """
)


class PostgresFTSRetriever:
    def search(self, db: Session, workspace_id: int, query: str, limit: int = 5) -> list[Citation]:
        query = (query or "").strip()[:1000]
        if not query:
            return []
        rows = db.execute(_SQL, {"query": query, "workspace_id": workspace_id, "limit": max(1, min(limit, 20))})
        return [
            Citation(
                document_id=r.document_id,
                document_title=r.title,
                chunk_id=r.id,
                chunk_index=r.chunk_index,
                heading=r.heading,
                snippet=r.snippet,
                content=r.content,
                score=round(float(r.score), 4),
            )
            for r in rows
        ]


def default_retriever() -> Retriever:
    return PostgresFTSRetriever()

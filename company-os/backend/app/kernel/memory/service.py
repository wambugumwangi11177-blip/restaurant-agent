"""
app/kernel/memory/service.py
────────────────────────────
Ingest documents into company memory. Idempotent on content: re-ingesting the
same text into the same workspace returns the existing document instead of
duplicating it (unique (workspace_id, content_hash)).
"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kernel.audit import write_audit
from app.kernel.events import emit
from app.kernel.memory.chunking import chunk_document
from app.kernel.models import Document, DocumentChunk
from app.kernel.tenancy import Principal

MAX_DOCUMENT_CHARS = 2_000_000


def ingest_text(
    db: Session, principal: Principal, title: str, content: str, source: str | None = None
) -> tuple[Document, bool]:
    """Returns (document, created)."""
    title = (title or "").strip()[:300]
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "title is required")
    if not content or not content.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "document is empty")
    if len(content) > MAX_DOCUMENT_CHARS:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "document exceeds 2,000,000 characters")
    content = content.replace("\x00", "")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = db.execute(
        select(Document).where(Document.workspace_id == principal.workspace_id, Document.content_hash == digest)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    doc = Document(
        workspace_id=principal.workspace_id, title=title, source=(source or None) and source[:500],
        content_hash=digest, content=content, created_by_user_id=principal.user_id,
    )
    db.add(doc)
    db.flush()
    chunks = chunk_document(content, title)
    for c in chunks:
        db.add(DocumentChunk(
            workspace_id=principal.workspace_id, document_id=doc.id, chunk_index=c.index,
            heading=c.heading, content=c.content, char_start=c.char_start, char_end=c.char_end,
        ))
    db.flush()
    write_audit(db, action="document.ingest", workspace_id=principal.workspace_id, entity_type="document",
                entity_id=doc.id, changes={"title": title, "chunks": len(chunks), "source": source},
                actor_user_id=principal.user_id)
    emit(db, "document.ingested", workspace_id=principal.workspace_id, entity_type="document", entity_id=doc.id,
         payload={"title": title, "chunks": len(chunks)}, actor_user_id=principal.user_id)
    return doc, True

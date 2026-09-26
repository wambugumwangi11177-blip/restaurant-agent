"""
app/api/memory.py
─────────────────
Company memory: add documents (JSON or file upload), list/read/delete them, and
search with citations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.db import get_db
from app.kernel.audit import write_audit
from app.kernel.memory.retriever import default_retriever
from app.kernel.memory.service import ingest_text
from app.kernel.models import Document, DocumentChunk, Link
from app.kernel.tenancy import Principal, get_or_404, scoped

router = APIRouter()

ALLOWED_UPLOAD_SUFFIXES = (".md", ".markdown", ".txt")
MAX_UPLOAD_BYTES = 4 * 1024 * 1024


class DocumentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    source: str | None = Field(default=None, max_length=500)


def _doc_out(doc: Document, chunks: int | None = None, with_content: bool = False) -> dict:
    out = {"id": doc.id, "title": doc.title, "source": doc.source, "created_at": doc.created_at.isoformat(),
           "chars": len(doc.content)}
    if chunks is not None:
        out["chunks"] = chunks
    if with_content:
        out["content"] = doc.content
    return out


@router.post("/memory/documents", status_code=201)
def add_document(body: DocumentIn, principal: Principal = Depends(require("memory.ingest")),
                 db: Session = Depends(get_db)) -> dict:
    doc, created = ingest_text(db, principal, body.title, body.content, body.source)
    db.commit()
    return {**_doc_out(doc), "created": created}


@router.post("/memory/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    principal: Principal = Depends(require("memory.ingest")),
    db: Session = Depends(get_db),
) -> dict:
    name = file.filename or "upload.txt"
    if not name.lower().endswith(ALLOWED_UPLOAD_SUFFIXES):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "Only .md and .txt are supported in Phase 0 (PDF/DOCX extraction is a later step)")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 4 MB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File must be UTF-8 text") from None
    doc, created = ingest_text(db, principal, title or name.rsplit(".", 1)[0], text, source=f"upload:{name}")
    db.commit()
    return {**_doc_out(doc), "created": created}


@router.get("/memory/documents")
def list_documents(principal: Principal = Depends(require("memory.search")), db: Session = Depends(get_db),
                   limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    counts = (select(DocumentChunk.document_id, func.count().label("n"))
              .where(DocumentChunk.workspace_id == principal.workspace_id)
              .group_by(DocumentChunk.document_id).subquery())
    rows = db.execute(
        scoped(Document, principal.workspace_id).add_columns(counts.c.n)
        .outerjoin(counts, counts.c.document_id == Document.id)
        .order_by(Document.id.desc()).limit(limit)
    ).all()
    return [_doc_out(doc, n or 0) for doc, n in rows]


@router.get("/memory/documents/{doc_id}")
def get_document(doc_id: int, principal: Principal = Depends(require("memory.search")),
                 db: Session = Depends(get_db)) -> dict:
    return _doc_out(get_or_404(db, Document, doc_id, principal.workspace_id), with_content=True)


@router.delete("/memory/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, principal: Principal = Depends(require("records.delete")),
                    db: Session = Depends(get_db)) -> None:
    doc = get_or_404(db, Document, doc_id, principal.workspace_id)
    write_audit(db, action="document.delete", workspace_id=principal.workspace_id, entity_type="document",
                entity_id=doc.id, changes={"title": doc.title}, actor_user_id=principal.user_id)
    db.execute(delete(Link).where(
        Link.workspace_id == principal.workspace_id,
        or_((Link.from_type == "document") & (Link.from_id == doc.id),
            (Link.to_type == "document") & (Link.to_id == doc.id)),
    ))
    db.delete(doc)
    db.commit()


@router.get("/memory/search")
def search(q: str = Query(min_length=1, max_length=500), limit: int = Query(default=5, ge=1, le=20),
           principal: Principal = Depends(require("memory.search")), db: Session = Depends(get_db)) -> dict:
    hits = default_retriever().search(db, principal.workspace_id, q, limit)
    return {"query": q, "results": [h.as_dict() for h in hits]}

"""
app/api/records.py
──────────────────
Generic CRUD for core records (/records/{type}) and links. Every write goes
through app.kernel.records, which adds the tenant filter, audit row and event.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import require
from app.db import get_db
from app.kernel import records
from app.kernel.schemas import LinkIn, LinkOut
from app.kernel.tenancy import Principal

router = APIRouter()


def _parse(model, body: Any):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, e.errors(include_url=False, include_context=False)) from None


def _out(type_name: str, obj) -> dict:
    return records.record_type(type_name).out.model_validate(obj).model_dump(mode="json")


@router.get("/records/{type_name}")
def list_records(
    type_name: str,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require("records.read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [_out(type_name, o) for o in records.list_records(db, principal, type_name, q, limit, offset)]


@router.post("/records/{type_name}", status_code=201)
def create_record(
    type_name: str,
    body: dict = Body(...),
    principal: Principal = Depends(require("records.write")),
    db: Session = Depends(get_db),
) -> dict:
    data = _parse(records.record_type(type_name).create, body)
    obj = records.create_record(db, principal, type_name, data)
    db.commit()
    return _out(type_name, obj)


@router.get("/records/{type_name}/{record_id}")
def get_record(type_name: str, record_id: int, principal: Principal = Depends(require("records.read")),
               db: Session = Depends(get_db)) -> dict:
    return _out(type_name, records.get_record(db, principal, type_name, record_id))


@router.patch("/records/{type_name}/{record_id}")
def update_record(
    type_name: str,
    record_id: int,
    body: dict = Body(...),
    principal: Principal = Depends(require("records.write")),
    db: Session = Depends(get_db),
) -> dict:
    patch = _parse(records.record_type(type_name).patch, body)
    obj = records.update_record(db, principal, type_name, record_id, patch)
    db.commit()
    return _out(type_name, obj)


@router.delete("/records/{type_name}/{record_id}", status_code=204)
def delete_record(type_name: str, record_id: int, principal: Principal = Depends(require("records.delete")),
                  db: Session = Depends(get_db)) -> None:
    records.delete_record(db, principal, type_name, record_id)
    db.commit()


@router.get("/records/{type_name}/{record_id}/links")
def record_links(type_name: str, record_id: int, principal: Principal = Depends(require("records.read")),
                 db: Session = Depends(get_db)) -> list[dict]:
    if type_name not in records.LINKABLE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown record type {type_name!r}")
    return [LinkOut.model_validate(lk).model_dump(mode="json") for lk in records.links_for(db, principal, type_name, record_id)]


@router.post("/links", status_code=201)
def create_link(body: LinkIn, principal: Principal = Depends(require("records.write")),
                db: Session = Depends(get_db)) -> dict:
    link = records.create_link(db, principal, body)
    db.commit()
    return LinkOut.model_validate(link).model_dump(mode="json")

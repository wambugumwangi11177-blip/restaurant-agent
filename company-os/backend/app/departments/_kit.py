"""
app/departments/_kit.py
───────────────────────
Shared building blocks for departments so each one stays small and uniform:
schema derivation (patch/out), money and currency fields, hook composition.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo
from sqlalchemy.orm import Session

from app.kernel.models import Workspace, _ts, _ws  # noqa: F401 — re-exported for department models
from app.kernel.tenancy import Principal

Money = Annotated[int, Field(ge=0, description="Minor units (cents). KES 1,500.00 = 150000")]
Currency = Annotated[Optional[str], Field(default=None, pattern=r"^[A-Z]{3}$")]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def patch_of(create: type[BaseModel]) -> type[BaseModel]:
    """Same fields and constraints as `create`, all optional (PATCH semantics)."""
    fields: dict[str, Any] = {}
    for name, f in create.model_fields.items():
        fields[name] = (Optional[f.annotation], FieldInfo.merge_field_infos(f, default=None))
    return create_model(create.__name__.replace("In", "") + "Patch", __base__=In, **fields)


def out_of(model: type) -> type[BaseModel]:
    """Response schema: every column except workspace_id / tsv."""
    fields = {c.key: (Any, None) for c in model.__table__.columns if c.key not in ("workspace_id", "tsv")}
    return create_model(model.__name__ + "Out", __config__=ConfigDict(from_attributes=True), **fields)


def default_currency(db: Session, principal: Principal, values: dict, obj: Any) -> dict:
    if obj is None and "currency" in values and not values.get("currency"):
        values["currency"] = db.get(Workspace, principal.workspace_id).currency
    return values


def chain(*hooks):
    def run(db, principal, values, obj):
        for h in hooks:
            values = h(db, principal, values, obj)
        return values
    return run


def money(minor: int | None, currency: str | None = "") -> str:
    if minor is None:
        return "—"
    return f"{currency or ''} {minor / 100:,.2f}".strip()


def iso(v: date | datetime | None) -> str:
    return v.isoformat() if v else "—"

"""
backend/ai/workflows/engine.py
────────────────────────────────
The durable workflow executor (Phase 8).

State lives in the DB (WorkflowRun / WorkflowStep), never in memory, so a run
survives a restart and can pause indefinitely on a human approval or an external
event. The executor is deterministic: it advances through auto steps
(agent_call / notify) until it reaches a pause step (human_approval /
wait_external), which it marks `awaiting` and stops on until `resume` is called.

No LLM here — the engine only sequences and persists. Each step's work is an
existing deterministic handler (templates.py). Mutations still respect the
human-approval hop: a low_stock_reorder cannot create a real purchase order until
the owner approves the draft.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

import models
from time_utils import utcnow
from .templates import TEMPLATES, HANDLERS

logger = logging.getLogger("ai.workflows")

_AUTO_TYPES = {"agent_call", "notify"}
_PAUSE_TYPES = {"human_approval", "wait_external"}


def start_workflow(db: Session, restaurant_id: int, template: str) -> dict:
    """Create a run + its steps from a template and advance to the first pause."""
    spec = TEMPLATES.get(template)
    if spec is None:
        return {"available": False, "error": f"Unknown workflow template '{template}'."}

    run = models.WorkflowRun(
        restaurant_id=restaurant_id, template=template,
        status="running", context_json="{}", current_step=0,
    )
    db.add(run)
    db.flush()
    for i, step in enumerate(spec):
        db.add(models.WorkflowStep(
            run_id=run.id, seq=i, name=step["name"], step_type=step["type"], status="pending",
        ))
    db.commit()
    db.refresh(run)
    return advance(db, run.id)


def advance(db: Session, run_id: int) -> dict:
    """Run auto steps until a pause step or completion. Idempotent per state."""
    run = db.query(models.WorkflowRun).filter(models.WorkflowRun.id == run_id).first()
    if run is None:
        return {"available": False, "error": "Workflow run not found."}
    if run.status in ("completed", "failed", "cancelled"):
        return serialize(db, run)

    spec = TEMPLATES.get(run.template, [])
    steps = _steps(db, run_id)
    ctx = _load_ctx(run)

    while run.current_step < len(spec):
        idx = run.current_step
        step = steps[idx]
        step_type = spec[idx]["type"]

        if step_type in _PAUSE_TYPES:
            step.status = "awaiting"
            run.status = "awaiting"
            db.commit()
            return serialize(db, run)

        # auto step (agent_call / notify)
        step.status = "running"
        db.commit()
        handler = HANDLERS.get(spec[idx].get("handler"))
        try:
            output = handler(db, run.restaurant_id, ctx) if handler else {}
            step.output_json = json.dumps(output, default=str)
            step.status = "done"
            step.completed_at = utcnow()
        except Exception as exc:  # noqa: BLE001 — a failed step fails the run cleanly
            step.error = str(exc)[:2000]
            step.status = "failed"
            run.status = "failed"
            db.commit()
            logger.warning("workflow %s step '%s' failed: %s", run_id, step.name, exc)
            return serialize(db, run)

        run.current_step = idx + 1
        _save_ctx(run, ctx)
        db.commit()

    run.status = "completed"
    db.commit()
    return serialize(db, run)


def resume(db: Session, run_id: int, decision: str = "approve", payload: dict | None = None) -> dict:
    """
    Resume a run paused on a human_approval or wait_external step.
      decision="approve" (default) or "reject" for approval steps. A rejection
      cancels the run (nothing downstream runs). wait_external steps ignore
      decision and just continue when the external event arrives.
    """
    run = db.query(models.WorkflowRun).filter(models.WorkflowRun.id == run_id).first()
    if run is None:
        return {"available": False, "error": "Workflow run not found."}
    if run.status != "awaiting":
        return {"available": False, "error": f"Run is '{run.status}', not awaiting resume."}

    steps = _steps(db, run_id)
    step = steps[run.current_step]
    ctx = _load_ctx(run)

    # A human_approval step advances ONLY on an explicit "approve" and cancels on
    # "reject" — any other value is rejected so an approval can never be advanced
    # by an ambiguous/typo'd decision. (wait_external steps just continue when the
    # external event arrives, regardless of decision.)
    if step.step_type == "human_approval":
        if decision == "reject":
            step.status = "done"
            step.output_json = json.dumps({"decision": "reject", **(payload or {})})
            step.completed_at = utcnow()
            run.status = "cancelled"
            db.commit()
            return serialize(db, run)
        if decision != "approve":
            return {"available": False,
                    "error": "Approval step needs an explicit decision: 'approve' or 'reject'."}

    step.status = "done"
    step.output_json = json.dumps({"decision": decision, **(payload or {})}, default=str)
    step.completed_at = utcnow()
    run.current_step += 1
    run.status = "running"
    _save_ctx(run, ctx)
    db.commit()
    return advance(db, run_id)


def cancel(db: Session, run_id: int) -> dict:
    run = db.query(models.WorkflowRun).filter(models.WorkflowRun.id == run_id).first()
    if run is None:
        return {"available": False, "error": "Workflow run not found."}
    if run.status in ("completed", "failed", "cancelled"):
        return serialize(db, run)
    run.status = "cancelled"
    db.commit()
    return serialize(db, run)


def get_run(db: Session, run_id: int) -> dict:
    run = db.query(models.WorkflowRun).filter(models.WorkflowRun.id == run_id).first()
    if run is None:
        return {"available": False, "error": "Workflow run not found."}
    return serialize(db, run)


# ── helpers ────────────────────────────────────────────────────────────────────

def _steps(db: Session, run_id: int) -> list[models.WorkflowStep]:
    return (
        db.query(models.WorkflowStep)
        .filter(models.WorkflowStep.run_id == run_id)
        .order_by(models.WorkflowStep.seq)
        .all()
    )


def _load_ctx(run: models.WorkflowRun) -> dict:
    try:
        return json.loads(run.context_json or "{}")
    except json.JSONDecodeError:
        return {}


def _save_ctx(run: models.WorkflowRun, ctx: dict) -> None:
    run.context_json = json.dumps(ctx, default=str)


def serialize(db: Session, run: models.WorkflowRun) -> dict:
    steps = _steps(db, run.id)
    return {
        "available": True,
        "id": run.id,
        "template": run.template,
        "status": run.status,
        "current_step": run.current_step,
        "context": _load_ctx(run),
        "steps": [
            {
                "seq": s.seq, "name": s.name, "type": s.step_type, "status": s.status,
                "output": _safe_json(s.output_json), "error": s.error,
            }
            for s in steps
        ],
    }


def _safe_json(text: str):
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}

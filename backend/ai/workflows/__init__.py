"""
backend/ai/workflows/
────────────────────────
Durable, stateful workflow engine (Phase 8). Long-running agentic processes —
stock-low → reorder → approve → deliver → update → notify — as a persisted state
machine that survives restarts and pauses on human approval / external events.
"""

from .engine import (  # noqa: F401
    start_workflow, advance, resume, cancel, get_run, serialize,
)
from .templates import template_names, TEMPLATES  # noqa: F401

"""
backend/ai/routing/
──────────────────────
Multi-model AI Router (Phase 7). Elevates ai/llm_client.py's tier system from
*metering* to *routing*: pick the right engine per request by capability, cost
and latency — and crucially, route deterministic/forecast tasks to NO LLM at all.
"""

from .router import choose_model, route_task, Route, NEED  # noqa: F401

"""
backend/ai/plugins/
──────────────────────
Marketplace / Plugin SDK (Phase 11). Third-party agents run on the platform
behind hard guardrails (read-only context, declared scopes, approval-gated
mutation) and contribute to the same Decision Intelligence ranking as the
built-in agents. See sdk.py for the contract.
"""

from .sdk import (  # noqa: F401
    PluginManifest, PluginContext, Plugin, PluginRegistry,
    registry, collect_plugin_decisions, ALLOWED_SCOPES, ALLOWED_PROVIDES,
)

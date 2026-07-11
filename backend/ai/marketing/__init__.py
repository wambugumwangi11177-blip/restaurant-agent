"""
backend/ai/marketing/
──────────────────────
Read-only marketing intelligence: turns what the deterministic agents already
know (lapsed regulars, high-margin under-sellers, stock at spoilage risk,
campaign send history) into specific, explained offers the owner can approve.

This module deliberately does NOT send anything on its own and holds no
autonomous scheduler — a previous autonomous `campaigns.py` was removed because
customer marketing needs consent-gating, opt-out, a cost ceiling and a kill
switch. Sending stays on the existing owner-approved WhatsApp path
(ai/whatsapp/brain.py: broadcast_promo / broadcast_winback), which is
consent-gated and opt-out-respecting.
"""

from .insights import get_marketing_insights  # noqa: F401

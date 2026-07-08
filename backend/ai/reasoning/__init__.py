"""
backend/ai/reasoning/
──────────────────────
The reasoning layer. Deterministic modules in ai/ produce the NUMBERS; this
layer turns those numbers into judgment (narrative, priorities, actions) using
an LLM that is never allowed to compute or invent figures. See narrator.py.
"""

from .narrator import narrate, TASKS  # noqa: F401

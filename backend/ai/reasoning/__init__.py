"""
backend/ai/reasoning/
──────────────────────
The reasoning layer. Deterministic modules in ai/ produce the NUMBERS; this
layer turns those numbers into judgment (narrative, priorities, actions) using
an LLM that is never allowed to compute or invent figures. See narrator.py.
"""

from .narrator import narrate, TASKS, get_trust_stats  # noqa: F401


def attach_narrative(data, task, restaurant_id, narrate_flag=True):
    """
    Attach an LLM `narrative` block to a deterministic analytics payload, if
    requested and the payload is a real result (not an error dict). Single home
    for the "narrate the numbers" wiring that the /ai/pricing, /ai/profit and
    /ai/menu-engineering routes all need — previously copy-pasted at each call
    site, where the menu-engineering copy had drifted (it lacked the error guard
    and so burned an LLM call on error payloads). Mutates and returns `data` for
    convenient one-line use at the routes.
    """
    if narrate_flag and isinstance(data, dict) and not data.get("error"):
        note = narrate(data, task, restaurant_id=restaurant_id)
        if note:
            data["narrative"] = note
    return data

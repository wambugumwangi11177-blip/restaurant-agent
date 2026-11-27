"""Plain owner help corpus for Ask OS + More."""
from fastapi import APIRouter, Depends

import auth
from routers.eleven_owner import _require_owner

router = APIRouter(prefix="/eleven/help", tags=["eleven-help"])

_PAGES = """
Home — today's sales, what needs your OK, what you're waiting on, done today.
Money — sales, costs, bills, dishes, cash; each chart opens for full numbers.
Stock — levels, reorder, handovers, suppliers, prep for the kitchen.
More — team, alerts, handovers, help, sign out.
Settings — reports schedule, targets, till and WhatsApp connections.
Ask OS — ask about any page or your live numbers in plain English.
""".strip()


@router.get("")
def help_index(current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    return {"pages": _PAGES, "locale": "en"}


@router.get("/sw")
def help_sw(current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    return {
        "pages": "Nyumbani — mauzo ya leo na maamuzi. Pesa — mauzo na bili. Stoo — bidhaa na wasambazaji.",
        "locale": "sw",
        "partial": True,
    }
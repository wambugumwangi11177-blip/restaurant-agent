"""The UI's permission matrix must agree with the gates the API enforces.

frontend/src/lib/permissions.ts says of itself: "UI-ONLY. The backend's
require_staff_role() gates are the actual authority — this file must be kept
in sync with them and with the matrix, or the UI will show something the API
then rejects."

Nothing enforced that. Two hand-maintained lists in two languages, one comment
asking someone to remember. This parses the real tuples out of the routers and
the real matrix out of the TypeScript, and fails when they drift — so a
convenient-looking loosening on either side is caught here rather than as a
Waiter clicking a link that 403s, or a Stockkeeper unable to reach a page the
API would have served them.

Same approach as test_os_question_routing.py, which parses osSuggestions.ts
for the same reason: the frontend is the spec for what the owner is offered.
"""
from __future__ import annotations

import pathlib
import re

import pytest

PERMISSIONS_TS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "lib" / "permissions.ts"
)


def _ui_matrix() -> dict[str, dict[str, str]]:
    """{domain: {tier: 'rw'|'r'}} parsed from the MATRIX literal."""
    src = PERMISSIONS_TS.read_text(encoding="utf-8")
    body = re.search(r"const MATRIX[^=]*=\s*\{(.*?)\n\};", src, re.S)
    assert body, "MATRIX literal not found — has permissions.ts been restructured?"
    out: dict[str, dict[str, str]] = {}
    for line in body.group(1).splitlines():
        m = re.match(r"\s*(\w+):\s*\{(.*)\},?\s*$", line)
        if not m:
            continue
        domain, entries = m.group(1), m.group(2)
        out[domain] = {
            t: a for t, a in re.findall(r"(\w+):\s*\"(rw|r)\"", entries)
        }
    assert out, "parsed no domains out of MATRIX"
    return out


def _tiers(tuple_expr) -> set[str]:
    """A backend _CAN_* tuple as lowercase tier names, OWNER dropped.

    Owner is Role.ADMIN and bypasses require_staff_role entirely, so it never
    appears in the UI matrix either (accessFor short-circuits it to 'rw')."""
    return {r.name.lower() for r in tuple_expr} - {"owner"}


@pytest.fixture(scope="module")
def ui():
    return _ui_matrix()


def _writers(ui_domain: dict[str, str]) -> set[str]:
    return {t for t, a in ui_domain.items() if a == "rw"}


def _readers(ui_domain: dict[str, str]) -> set[str]:
    return set(ui_domain)


# ── Domain by domain ─────────────────────────────────────────────────────────

def test_orders_agrees(ui):
    from routers import orders
    assert _writers(ui["orders"]) == _tiers(orders._CAN_WRITE)
    assert _readers(ui["orders"]) == _tiers(orders._CAN_READ)


def test_inventory_agrees(ui):
    from routers import inventory
    assert _writers(ui["inventory"]) == _tiers(inventory._CAN_WRITE)
    assert _readers(ui["inventory"]) == _tiers(inventory._CAN_READ)


def test_menu_write_agrees(ui):
    from routers import menu
    assert _writers(ui["menu"]) == _tiers(menu._CAN_WRITE)


def test_reservations_write_agrees(ui):
    from routers import reservations
    assert _writers(ui["reservations"]) == _tiers(reservations._CAN_WRITE)


def test_purchasing_readers_agree(ui):
    from routers import purchase_orders
    assert _readers(ui["purchasing"]) == _tiers(purchase_orders._CAN_READ)


# ── Separation of duties, on both sides ──────────────────────────────────────

def test_the_controller_can_read_inventory_and_never_write_it(ui):
    """Directive 015's whole reason for the Controller role: the person
    reconciling a variance must not be the person who could cover a shortfall.
    Asserted on BOTH sides, because collapsing it anywhere defeats it."""
    from routers import inventory, stock_custody

    assert ui["inventory"].get("controller") == "r"
    assert "controller" not in _writers(ui["inventory"])

    controller = {"controller"}
    assert not (controller & _tiers(inventory._CAN_WRITE))
    assert controller & _tiers(inventory._CAN_READ)
    # ...and cannot move stock through the custody routes either.
    assert not (controller & _tiers(stock_custody._CAN_INITIATE))
    assert not (controller & _tiers(stock_custody._CAN_FULFILL))
    # But CAN count — a surprise count by someone who cannot move stock is the
    # standard internal-audit control.
    assert controller & _tiers(stock_custody._CAN_COUNT)
    # And can read the variance report they are there to act on.
    assert controller & _tiers(stock_custody._CAN_READ_VARIANCE)


def test_front_of_house_cannot_read_the_variance_report(ui):
    """The subject of a theft investigation must not be able to read it."""
    from routers import stock_custody, fraud
    allowed = _tiers(stock_custody._CAN_READ_VARIANCE) | _tiers(fraud._CAN_READ)
    assert not ({"waiter", "kitchen"} & allowed)


def test_no_ui_domain_grants_a_tier_the_api_does_not(ui):
    """The failure that matters to a user: a visible link that 403s."""
    from routers import orders, inventory, menu, reservations, purchase_orders

    checks = [
        ("orders", orders._CAN_READ),
        ("inventory", inventory._CAN_READ),
        ("purchasing", purchase_orders._CAN_READ),
    ]
    for domain, api_tuple in checks:
        extra = _readers(ui[domain]) - _tiers(api_tuple)
        assert not extra, f"UI shows {domain} to {extra}, which the API rejects"

    for domain, api_tuple in [("menu", menu._CAN_WRITE),
                              ("reservations", reservations._CAN_WRITE)]:
        extra = _writers(ui[domain]) - _tiers(api_tuple)
        assert not extra, f"UI offers writes on {domain} to {extra}, which the API rejects"


def test_the_matrix_parses_every_domain_the_ui_declares(ui):
    """A domain silently dropped from the parse would make every assertion
    above vacuously pass."""
    src = PERMISSIONS_TS.read_text(encoding="utf-8")
    # Scope to the Domain declaration — StaffTier is the same shape one
    # declaration above, and matching both made this compare domains against
    # role names.
    block = re.search(r"export type Domain\s*=(.*?);", src, re.S)
    assert block, "could not find the Domain union"
    declared = set(re.findall(r"\"(\w+)\"", block.group(1)))
    # The Domain union and the MATRIX keys must be the same set.
    assert declared, "could not parse the Domain union"
    assert set(ui) == declared, f"MATRIX and Domain disagree: {set(ui) ^ declared}"

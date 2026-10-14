"""Compliance: a deterministic calendar so no statutory date depends on memory.
Confirm every item with a Kenyan advocate / KRA-licensed tax agent."""
import os
from datetime import date

from .. import kernel, tools  # noqa: F401

NAME = "compliance"


def due_items(today: date) -> list[tuple[str, str]]:
    """(key, text) pairs due today. Keys make each reminder fire once per period."""
    items = []
    if os.getenv("COMPANY_HAS_EMPLOYEES", "").lower() in ("1", "true", "yes") and today.day == 2:
        items.append((f"paye-{today:%Y-%m}", "PAYE for last month is due by the 9th (KRA)."))
    if today.day == 1 and today.month in (1, 4, 7, 10):
        items.append((f"restore-{today:%Y-%m}", "Quarterly: run a production restore drill and an access review (DISASTER_RECOVERY.md section 2)."))
    if today.month == 7 and today.day == 1:
        items.append((f"finact-{today.year}", "Finance Act takes effect: review tax rates, VAT threshold and eTIMS rules with your tax agent."))
    if today.day == 1:
        items.append((f"models-{today:%Y-%m}", "Monthly: check Anthropic model deprecations and update RETIRING_MODELS."))
        items.append((f"ledger-{today:%Y-%m}", "Monthly: accountant closes the month; confirm every expense has an eTIMS invoice."))
    for mmdd, key, text in _annual():
        if (today.month, today.day) == mmdd:
            items.append((f"{key}-{today.year}", text))
    return items


def _annual():
    """Company-specific dates from COMPANY_ANNUAL_DEADLINES='MM-DD:key:text;...'."""
    for part in filter(None, os.getenv("COMPANY_ANNUAL_DEADLINES", "").split(";")):
        try:
            md, key, text = part.split(":", 2)
            m, d = md.split("-")
            yield (int(m), int(d)), key, text
        except ValueError:
            continue


def run(db, today=None):
    out, today = [], today or date.today()
    for key, text in due_items(today):
        summary = f"Compliance {key}"
        if kernel.already_proposed(db, "operator_alert", summary, 20):
            continue
        out.append(kernel.propose(
            db, "compliance.calendar_agent", "operator_alert",
            {"title": "Compliance reminder", "body": text, "event_type": "company_compliance"}, summary))
    return out

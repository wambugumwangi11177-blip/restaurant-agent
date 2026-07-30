"""
execution/emit_capability_manifest.py
────────────────────────────────────────
Emit a machine-checkable list of "we told a prospect X, and it's backed by code Y" —
the seam between this repo and the sibling `leviii-gtm` repo, which holds all sales
collateral and cannot see this source tree.

Why this exists: directive 015 (moved to leviii-gtm as 001_sales_and_marketing.md)
sets a standing rule that every capability claim names the function that implements
it. That rule only holds if someone re-checks it by hand every time the code moves.
This script re-checks it by machine: for every CLAIM below, it verifies the target
file exists and (if a symbol is given) that the symbol still appears in it. Ship
drift — a rename, a deletion, a refactor — turns into a FAIL here instead of a
silent lie in a sales deck three weeks later.

This is intentionally NOT auto-discovered from a docstring convention. Claims are
declared by hand in CLAIMS below, each time collateral in leviii-gtm cites new
code. That keeps the list of "things we promise" reviewable in one diff, rather
than whatever a heuristic happened to scrape.

Usage:
    uv run python execution/emit_capability_manifest.py
    uv run python execution/emit_capability_manifest.py --check   # exit 1 on any FAIL, no write

Output: .tmp/capability-manifest.json (an intermediate, per this repo's file rules —
never committed here). Copy this file into leviii-gtm/contract/capability-manifest.json
after every run where it changed — that committed copy is what contract/verify_claims.py
in the GTM repo checks sales docs against.

NOTE: `python` is not on PATH here (Microsoft Store stub) - use `uv run python`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / ".tmp" / "capability-manifest.json"

# Each claim: id used by sales docs to cite it, the file it lives in (repo-relative),
# the symbol that must appear in that file (None = file-existence claim only), the
# status shown to prospects, and the one-line claim text as it appears in collateral.
CLAIMS = [
    dict(
        id="profit-leak-detection",
        file="backend/ai/profit/intelligence.py",
        symbol="_detect_profit_leaks",
        status="Built",
        claim="Detects profit leaks (till charging less than menu price) from order history",
    ),
    dict(
        id="portion-drift-detection",
        file="backend/ai/profit/intelligence.py",
        symbol="_detect_portion_drift",
        status="Built",
        claim="Detects portion drift patterns invisible to a standard POS",
    ),
    dict(
        id="decisions-never-invent-numbers",
        file="backend/ai/decisions/model.py",
        symbol="impact_cents_month",
        status="Built",
        claim="AI never calculates money; impact_cents_month stays None when unquantified",
    ),
    dict(
        id="roi-three-totals-never-summed",
        file="backend/ai/roi/savings.py",
        symbol="get_roi_savings",
        status="Built",
        claim="Three ROI totals computed and deliberately never summed into one figure",
    ),
    dict(
        id="pii-scrubbing",
        file="backend/ai/pii_scrub.py",
        symbol=None,
        status="Built",
        claim="PII stripped before any model call",
    ),
    dict(
        id="data-export",
        file="backend/routers/export.py",
        symbol=None,
        status="Built",
        claim="Full data export and erasure available",
    ),
    dict(
        id="webhook-idempotency",
        file="backend/routers/webhooks.py",
        symbol="idempotency",
        status="Built",
        claim="M-Pesa callbacks reconcile idempotently — duplicates ignored",
    ),
    dict(
        id="cross-branch-benchmarking",
        file="backend/ai/enterprise/benchmarking.py",
        symbol=None,
        status="Built",
        claim="Every branch ranked on one screen",
    ),
    dict(
        id="chain-wide-audit-trail",
        file="backend/ai/enterprise/audit_center.py",
        symbol=None,
        status="Built",
        claim="One chain-wide audit trail across branches",
    ),
    dict(
        id="whatif-simulation",
        file="backend/ai/simulation/twin.py",
        symbol=None,
        status="Built",
        claim="Test a price change before touching a real order (digital twin)",
    ),
    dict(
        id="rbac-role-model",
        file="backend/models.py",
        symbol="class Role",
        status="Built",
        claim="Role-based permission model exists (Role enum, require_role dependency)",
    ),
    dict(
        id="prometheus-metrics-endpoint",
        file="backend/main.py",
        symbol="/metrics",
        status="Built",
        claim="A /metrics endpoint exists — NOT the same claim as 'uptime monitoring/alerting is wired'",
    ),
    dict(
        id="uptime-alerting-paging",
        file=None,
        symbol=None,
        status="Coming soon",
        claim="Automatic SEV-1 paging / 15-min incident response / SLA credits — NOT wired as of "
        "docs/sla-remediation.md E1. Do not promise fixed response-time SLAs until this ships.",
    ),
    dict(
        id="cash-up-drawer-reconciliation",
        file=None,
        symbol=None,
        status="Coming soon",
        claim="No cash-up / drawer / till-count / declared-cash feature exists in backend/ "
        "(docs/pain-library.md P3). Do not claim this capability.",
    ),
]


def check_claim(c: dict) -> dict:
    result = dict(c)
    if c["file"] is None:
        # Explicit "does not exist yet" claims are self-verifying: Coming soon, no file to check.
        result["verified"] = c["status"] == "Coming soon"
        result["note"] = "negative claim (absence) — not machine-checkable beyond status"
        return result

    path = REPO / c["file"]
    if not path.exists():
        result["verified"] = False
        result["note"] = f"FILE NOT FOUND: {c['file']}"
        return result

    if c["symbol"] is None:
        result["verified"] = True
        result["note"] = "file exists; no specific symbol required"
        return result

    text = path.read_text(encoding="utf-8", errors="replace")
    if c["symbol"] in text:
        result["verified"] = True
        result["note"] = f"symbol '{c['symbol']}' found"
    else:
        result["verified"] = False
        result["note"] = f"SYMBOL NOT FOUND: '{c['symbol']}' no longer in {c['file']}"
    return result


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 on any failed claim, don't write")
    args = ap.parse_args()

    checked = [check_claim(c) for c in CLAIMS]
    failures = [c for c in checked if not c["verified"]]

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_repo_commit": git_sha(),
        "claims": checked,
    }

    print(f"{len(checked)} claims checked, {len(failures)} failed.\n")
    for c in checked:
        mark = "OK  " if c["verified"] else "FAIL"
        print(f"  [{mark}] {c['id']:35s} {c['note']}")

    if not args.check:
        OUT.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"\nWrote {OUT}")
        print("Copy this file to ../leviii-gtm/contract/capability-manifest.json")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

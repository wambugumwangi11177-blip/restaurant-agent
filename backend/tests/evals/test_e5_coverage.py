"""
E5 — Screen coverage (docs/v2/SPEC.md §5): nothing is built and left invisible.

Every entry of `owner/registry.py` must appear on Home, be answerable in Ask LEVIII (OS), and be in at least one
report. The check runs against the REAL composed payloads of the golden restaurant, not against the registry's
own claims: a declared Home block that is not in `/owner/home`, an OS topic that has no handler, or a report
section that has no builder is a gap, however the registry words it.

Per entry and surface the verdict is one of
    present      the engine's output is on that surface (built block / answerable topic / built report section)
    planned      listed (a placeholder block or a report section named in PLAN) but not built yet
    exempt       correctly not there — the registry gives a written reason
    missing      nothing is declared for it
and, for an engine that is itself not built yet (`status="planned"`), its placeholders are not gaps.

A *gap* is a built engine that is `planned` or `missing` on a surface without an exemption. S1.4 is allowed to have
gaps (SPEC S1.4: "allowed to fail per-entry until P4, but the report must be produced"); the allow-list below is
the debt, and it may only SHRINK:

  * a gap that is not in the allow-list fails this test (a new engine cannot be built and left invisible);
  * an allow-listed gap that has been closed also fails, until its entry is deleted (so the list shrinks, and
    nobody can quietly re-open a closed gap);
  * P4's exit criterion is `ALLOWED_GAPS == {}`.

`E5_WRITE_REPORT=1` (set by `make -C docs/v2 evals`) writes the matrix to docs/v2/e5-coverage.md.

Not checked here (S2.1 owns it): that the demo tenant gives *non-empty* output from every engine. This eval is
about wiring — whether the block, topic and section exist — which does not depend on the data in the fixture.
"""
import os
from pathlib import Path

import pytest

from owner import registry, reports
from owner.home import compose_home
from owner.states import OwnerContext
from tests.fixtures import golden_restaurant as gr

REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "v2" / "e5-coverage.md"

# The debt: (engine, surface) -> where it is paid off. May only shrink.
_OS = "S5.1 (Ask LEVIII answers every area in five forms)"
_REPORT = "S5.2 (report sections built)"
_P4 = "S4.x (Home v2 blocks)"
ALLOWED_GAPS: dict[tuple[str, str], str] = {
    ("revenue_forecast", "reports"): _REPORT,
    ("profit", "reports"): _REPORT,
    ("pricing", "reports"): _REPORT,
    ("menu", "reports"): _REPORT,
    ("inventory", "reports"): _REPORT,
    ("custody", "reports"): _REPORT,
    ("cash", "os"): _OS, ("cash", "reports"): _REPORT,
    ("fraud", "os"): _OS, ("fraud", "reports"): _REPORT,
    ("kds", "reports"): _REPORT,
    ("reservations", "reports"): _REPORT,
    ("labor", "reports"): _REPORT,
    ("supply_chain", "os"): _OS, ("supply_chain", "reports"): _REPORT,
    ("marketing", "os"): _OS, ("marketing", "reports"): _REPORT,
    ("roi", "os"): _OS, ("roi", "reports"): _REPORT,
    ("twin", "reports"): _REPORT,
    ("data_quality", "os"): _OS, ("data_quality", "reports"): _REPORT,
    ("simulator", "os"): _OS,
    ("strategist", "os"): _OS,
    ("decisions", "reports"): _REPORT,
    ("owner_settings", "reports"): _REPORT,
}


# ── resolve the registry against the real payloads ───────────────────────────

@pytest.fixture
def payloads(db_session):
    """Compose Home for the golden restaurant (a week of sales is enough: block presence is not data-dependent)."""
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g)
    return {"home": compose_home(OwnerContext(db_session, g.owner, g.restaurant), "today")}


def _resolve(home: dict, path: str):
    """A registry block path → the dict in the composed Home payload, or None."""
    parts = path.split(".")
    if len(parts) == 1:
        return home.get(parts[0])
    head, name = parts
    if head == "coming_up":
        return home["coming_up"].get(name)
    return home["areas"].get(head, {}).get("blocks", {}).get(name)


def coverage(home: dict) -> dict[str, dict[str, str]]:
    built, planned = reports.built_sections(), reports.planned_sections()
    from owner import ask
    topics = set(ask.topics())
    out: dict[str, dict[str, str]] = {}
    for e in registry.ENGINES:
        row: dict[str, str] = {}
        # Home
        found = [b for b in (_resolve(home, p) for p in e.home_blocks)]
        if e.home_blocks and all(b is not None for b in found):
            row["home"] = "present" if e.status == "built" else "planned"
        else:
            row["home"] = "missing"
        # OS
        row["os"] = "present" if e.os_topics and set(e.os_topics) <= topics else "missing"
        # reports
        if any(s in built for s in e.report_sections):
            row["reports"] = "present"
        elif any(s in planned for s in e.report_sections):
            row["reports"] = "planned"
        else:
            row["reports"] = "missing"
        for surface in registry.SURFACES:
            if surface in e.exemptions and row[surface] != "present":
                row[surface] = "exempt"
        out[e.key] = row
    return out


def gaps(cov: dict[str, dict[str, str]]) -> set[tuple[str, str]]:
    found = set()
    for key, row in cov.items():
        if registry.BY_KEY[key].status == "planned":
            continue                      # an engine that is not built is not a wiring gap; its sprint builds the surfaces
        for surface, verdict in row.items():
            if verdict in ("planned", "missing"):
                found.add((key, surface))
    return found


# ── the eval ─────────────────────────────────────────────────────────────────

def test_declared_home_blocks_are_really_in_the_home_payload(payloads):
    """A registry entry cannot claim a Home block that /owner/home does not carry."""
    missing = [(e.key, p) for e in registry.ENGINES for p in e.home_blocks if _resolve(payloads["home"], p) is None]
    assert missing == [], f"registry declares Home blocks that are not in the payload: {missing}"


def test_every_home_block_belongs_to_a_registered_engine(payloads):
    """The converse: nothing on Home is there without an engine accounting for it (no orphan blocks)."""
    home = payloads["home"]
    on_home = {"pulse", "costing_you_money", "health", "read"}
    on_home |= {f"coming_up.{name}" for name in home["coming_up"]}
    on_home |= {f"{area}.{name}" for area, a in home["areas"].items() for name in a["blocks"]}
    claimed = {p for e in registry.ENGINES for p in e.home_blocks}
    orphans = sorted(on_home - claimed - set(registry.NOT_ENGINE_BLOCKS))
    assert orphans == [], f"blocks on Home that no registry entry owns (register the engine or drop the block): {orphans}"


def test_planned_engines_are_honest_placeholders_on_home(payloads):
    """An engine that is not built yet has only `unavailable` blocks with a reason — except the blocks the registry says are
    already built (a partly built engine, e.g. the P&L before break-even and bills)."""
    for e in registry.engines("planned"):
        for path in e.home_blocks:
            block = _resolve(payloads["home"], path)
            if path in e.built_blocks:
                assert block["state"] != "unavailable", f"{e.key}: {path} is declared built but is a placeholder"
            else:
                assert block["state"] == "unavailable" and block.get("reason"), f"{e.key}: {path} pretends to be built"


def test_built_engines_are_never_stubbed_on_home(payloads):
    """A built engine's block may be no_data (nothing recorded) but must not be a hard-coded 'unavailable' stub
    on a restaurant that has sales, stock and staff — that would be an engine built and left invisible."""
    stubs = []
    for e in registry.engines("built"):
        for path in e.home_blocks:
            block = _resolve(payloads["home"], path)
            if block["state"] == "unavailable" and "could not be read" in (block.get("reason") or ""):
                stubs.append((e.key, path, block["reason"]))
    assert stubs == [], f"engine failures on the golden restaurant: {stubs}"


def test_exemptions_are_few_and_reasoned():
    for e in registry.ENGINES:
        for surface, reason in e.exemptions.items():
            assert len(reason) > 25, (e.key, surface)
    assert sum(len(e.exemptions) for e in registry.ENGINES) <= 6, "exemptions are for exceptions; wire the engine instead"


def test_coverage_gaps_equal_the_allow_list_and_only_shrink(payloads):
    cov = coverage(payloads["home"])
    actual = gaps(cov)
    allowed = set(ALLOWED_GAPS)
    new = sorted(actual - allowed)
    closed = sorted(allowed - actual)
    assert new == [], f"NEW coverage gaps — an engine is not on a surface. Wire it (or exempt it with a reason): {new}"
    assert closed == [], f"gaps closed — delete them from ALLOWED_GAPS (the list may only shrink): {closed}"


def test_home_is_complete_for_every_built_engine(payloads):
    """The surface the owner opens first has no gaps today: every built engine is on Home."""
    cov = coverage(payloads["home"])
    assert [k for k, row in cov.items() if row["home"] in ("missing",) and registry.BY_KEY[k].status == "built"] == []


def test_write_the_coverage_report(payloads):
    cov = coverage(payloads["home"])
    text = render(cov)
    assert "| engine |" in text
    if os.environ.get("E5_WRITE_REPORT") == "1":
        REPORT_PATH.write_text(text, encoding="utf-8")
        print(f"\n[E5] wrote {REPORT_PATH}")
    else:
        assert REPORT_PATH.exists(), "run `make -C docs/v2 evals` (E5_WRITE_REPORT=1) to produce docs/v2/e5-coverage.md"
        assert REPORT_PATH.read_text(encoding="utf-8") == text, (
            "docs/v2/e5-coverage.md is stale — run `make -C docs/v2 evals` and commit the result")


# ── the report ───────────────────────────────────────────────────────────────

_SYMBOL = {"present": "✔", "planned": "◌ planned", "missing": "✖ missing", "exempt": "— exempt"}


def render(cov: dict[str, dict[str, str]]) -> str:
    built = registry.engines("built")
    rows = []
    for e in registry.ENGINES:
        row = cov[e.key]
        cells = []
        for surface in registry.SURFACES:
            verdict = row[surface]
            if e.status == "planned" and verdict in ("planned", "missing"):
                cells.append(f"◌ {e.planned_in}")
            else:
                cells.append(_SYMBOL[verdict])
        rows.append(f"| {e.key} | {e.owner_name} | {e.status} | " + " | ".join(cells) + " |")
    actual = sorted(gaps(cov))
    complete = sum(1 for e in built if all(cov[e.key][s] in ("present", "exempt") for s in registry.SURFACES))
    lines = [
        "# E5 — screen coverage (generated by `backend/tests/evals/test_e5_coverage.py`; do not edit)",
        "",
        "Source of truth: `backend/owner/registry.py`, checked against the composed `/owner/home` payload, the Ask LEVIII",
        "topics (`routers/ai_ask.py`) and the report plan (`owner/reports.py`). ✔ present · ◌ planned (placeholder or",
        "named in the report plan, not built) · — exempt (written reason in the registry) · ✖ missing.",
        "",
        f"**{len(registry.ENGINES)} registered engines · {len(built)} built · {complete} complete on all three surfaces · "
        f"{len(actual)} open gaps** (P4 exit: 0).",
        "",
        "| engine | owner name | status | Home | OS | Reports |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        "## Open gaps (the allow-list; may only shrink)",
        "",
    ]
    by_surface: dict[str, list[str]] = {}
    for key, surface in actual:
        by_surface.setdefault(surface, []).append(key)
    for surface in registry.SURFACES:
        if surface in by_surface:
            lines.append(f"- **{surface}** ({len(by_surface[surface])}): " + ", ".join(by_surface[surface])
                         + f" — {next(ALLOWED_GAPS[(k, surface)] for k in by_surface[surface] if (k, surface) in ALLOWED_GAPS)}")
    lines += ["", "## Not yet built engines (their surfaces are placeholders until their sprint)", ""]
    for e in registry.engines("planned"):
        lines.append(f"- **{e.key}** — {e.owner_name}: {e.planned_in}")
    lines += ["", "## Exemptions (written reasons)", ""]
    for e in registry.ENGINES:
        for surface, reason in e.exemptions.items():
            lines.append(f"- **{e.key}** / {surface}: {reason}")
    lines += ["", "## Not engines (resolved candidates from the code map)", ""]
    for module, reason in registry.NOT_ENGINES.items():
        lines.append(f"- `{module}`: {reason}")
    return "\n".join(lines) + "\n"

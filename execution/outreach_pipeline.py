"""
execution/outreach_pipeline.py
───────────────────────────────
The lead pipeline for door-to-door and cold-call outreach — see
`directives/015_cold_outreach.md` for the field play this supports.

Why a script instead of a spreadsheet: a field pipeline lives or dies on being
updated in the car park thirty seconds after the visit, and on being *countable*
afterwards. A CSV plus a handful of subcommands is faster to update than a
spreadsheet on a phone, and it makes the funnel arithmetic (`stats`) exact
rather than remembered. Stage transitions are validated, so a lead can never end
up in a state the funnel maths doesn't understand.

Storage: `outreach/pipeline.csv`, git-ignored. This file holds real names and
phone numbers of people who have not agreed to anything — it is exactly the kind
of personal data this project's own compliance posture (`docs/compliance/`) says
must not be committed. Keep it local, back it up yourself.

Append-only touch log: every call/visit is a row in `outreach/touches.csv`, never
an overwrite, so "we spoke twice and they went quiet" survives contact with
memory.

Commands
    add    NAME [--area --phone --contact --notes]   register a lead
    log    ID --outcome X [--note --at]              record a visit/call
    stage  ID STAGE [--next YYYY-MM-DD --note]       move a lead's stage
    list   [--stage --area --all]                    show the pipeline
    today  [--date YYYY-MM-DD]                       who to chase today
    show   ID                                        one lead + full history
    stats                                            funnel conversion

All commands are read-only against the app database — this tool never touches
the restaurant product's data, only the outreach files.
"""

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "outreach"
LEADS_CSV = DATA_DIR / "pipeline.csv"
TOUCHES_CSV = DATA_DIR / "touches.csv"

# Ordered: index position IS the funnel depth, which is what makes `stats` able
# to compute stage-to-stage conversion without a separate mapping to drift.
STAGES = [
    "new",           # on the list, never contacted
    "contacted",     # spoke to someone, not the decision-maker
    "qualified",     # decision-maker engaged and a real fit
    "demo_booked",   # a time is in the calendar
    "demo_done",     # demo happened
    "proposal",      # pricing sent, deciding
    "won",           # signed
]
# Terminal states, deliberately outside the funnel order: they are exits, not
# depths, and counting them as progress would flatter every conversion number.
TERMINAL = ["lost", "cold", "disqualified"]
ALL_STAGES = STAGES + TERMINAL

# States that need no further chasing. `won` is a success rather than a terminal
# state, but it belongs here for `today`/`list`: a signed customer is not a lead,
# and leaving them on the daily chase list is how the list stops being trusted.
CLOSED = set(TERMINAL) | {"won"}

OUTCOMES = [
    "no_answer",     # nobody reachable
    "gatekeeper",    # spoke to staff, decision-maker absent — get name + best time
    "brush_off",     # decision-maker declined to engage
    "conversation",  # a real conversation happened
    "booked",        # a demo time was agreed
    "demo",          # the demo itself
    "follow_up",     # a chase message or call
]

LEAD_FIELDS = [
    "id", "name", "area", "phone", "contact", "stage", "peak_stage",
    "next_action_date", "created", "updated", "notes",
]
TOUCH_FIELDS = ["lead_id", "at", "outcome", "note"]


# ── storage ──────────────────────────────────────────────────────────────────

def _ensure_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not LEADS_CSV.exists():
        _write_leads([])
    if not TOUCHES_CSV.exists():
        with TOUCHES_CSV.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, TOUCH_FIELDS).writeheader()
    # A pipeline of real prospects' phone numbers must never reach git. Written
    # here rather than the repo's .gitignore so the protection travels with the
    # data directory even if someone copies it elsewhere.
    gitignore = DATA_DIR / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# Real prospect contact data — never commit.\n*\n")


def _read_leads() -> list[dict]:
    _ensure_files()
    with LEADS_CSV.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_leads(leads: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    # Write-then-replace: a crash mid-write must not leave a truncated pipeline,
    # since this file is the only copy of the field team's work.
    tmp = LEADS_CSV.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, LEAD_FIELDS)
        writer.writeheader()
        writer.writerows(leads)
    tmp.replace(LEADS_CSV)


def _read_touches() -> list[dict]:
    _ensure_files()
    with TOUCHES_CSV.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _append_touch(lead_id: str, outcome: str, note: str, at: str) -> None:
    _ensure_files()
    with TOUCHES_CSV.open("a", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, TOUCH_FIELDS).writerow(
            {"lead_id": lead_id, "at": at, "outcome": outcome, "note": note}
        )


def _find(leads: list[dict], lead_id: str) -> dict:
    for lead in leads:
        if lead["id"] == str(lead_id):
            return lead
    sys.exit(f"[ERROR] No lead with id {lead_id}. Run `list` to see ids.")


def _today() -> str:
    return date.today().isoformat()


# ── funnel depth ─────────────────────────────────────────────────────────────
# A lead's *current* stage forgets how far it got: a prospect who reached
# demo_done and then went `lost` reads as a bare "lost", and the demo→won ratio
# silently loses its denominator — the exact number directive 015 says to steer
# on. `peak_stage` remembers the deepest point instead, so exits stop distorting
# the funnel.

def _depth(stage: str) -> int:
    """Funnel depth of a stage; terminal states have no depth of their own."""
    return STAGES.index(stage) if stage in STAGES else -1


def _deeper(a: str, b: str) -> str:
    """Whichever of two stages sits deeper in the funnel."""
    return a if _depth(a) >= _depth(b) else b


def _peak_of(lead: dict) -> str:
    """
    A lead's deepest stage, tolerating rows written before `peak_stage` existed
    (and hand-edited CSVs, which happen) by falling back to the current stage.
    """
    peak = (lead.get("peak_stage") or "").strip()
    return peak if peak in STAGES else (lead["stage"] if lead["stage"] in STAGES else "new")


def _valid_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        sys.exit(f"[ERROR] '{value}' is not a date. Use YYYY-MM-DD.")


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_add(args) -> None:
    leads = _read_leads()
    if any(lead["name"].strip().lower() == args.name.strip().lower()
           and lead["area"].strip().lower() == (args.area or "").strip().lower()
           for lead in leads):
        # Walking the same street twice is normal; re-adding the same restaurant
        # silently would double-count it in every conversion number.
        sys.exit(f"[ERROR] '{args.name}' in {args.area or '(no area)'} is already in the pipeline.")

    next_id = str(max((int(lead["id"]) for lead in leads), default=0) + 1)
    leads.append({
        "id": next_id,
        "name": args.name,
        "area": args.area or "",
        "phone": args.phone or "",
        "contact": args.contact or "",
        "stage": "new",
        "peak_stage": "new",
        "next_action_date": args.next or "",
        "created": _today(),
        "updated": _today(),
        "notes": args.notes or "",
    })
    _write_leads(leads)
    print(f"[OK] Added #{next_id}  {args.name} ({args.area or 'no area'})  stage=new")


def cmd_log(args) -> None:
    leads = _read_leads()
    lead = _find(leads, args.id)
    at = _valid_date(args.at) if args.at else _today()
    _append_touch(lead["id"], args.outcome, args.note or "", at)

    # A touch is evidence of contact, so a lead sitting in `new` after a real
    # conversation is simply wrong — advance it rather than making the operator
    # remember a second command in a car park.
    if lead["stage"] == "new" and args.outcome != "no_answer":
        lead["stage"] = "contacted"
        print(f"[OK] #{lead['id']} auto-advanced new → contacted")
    if args.next:
        lead["next_action_date"] = _valid_date(args.next)
    lead["updated"] = at
    _write_leads(leads)

    print(f"[OK] Logged {args.outcome} for #{lead['id']} {lead['name']} on {at}")
    if args.outcome == "gatekeeper" and not args.note:
        print("     TIP: log the decision-maker's NAME and BEST TIME in --note — "
              "that, not the phone number, is what makes the return visit work.")


def cmd_stage(args) -> None:
    leads = _read_leads()
    lead = _find(leads, args.id)
    if args.stage not in ALL_STAGES:
        sys.exit(f"[ERROR] Unknown stage '{args.stage}'. One of: {', '.join(ALL_STAGES)}")

    previous = lead["stage"]
    lead["stage"] = args.stage
    lead["peak_stage"] = _deeper(_peak_of(lead), args.stage)
    lead["updated"] = _today()
    if args.next:
        lead["next_action_date"] = _valid_date(args.next)
    elif args.stage in TERMINAL:
        lead["next_action_date"] = ""  # a dead lead must stop appearing in `today`
    if args.note:
        lead["notes"] = (lead["notes"] + " | " if lead["notes"] else "") + args.note
    _write_leads(leads)
    _append_touch(lead["id"], "stage_change", f"{previous} → {args.stage}", _today())

    print(f"[OK] #{lead['id']} {lead['name']}: {previous} → {args.stage}")
    if args.stage == "demo_booked" and not lead["next_action_date"]:
        print("     WARN: no demo date set. Use --next YYYY-MM-DD — an unconfirmed "
              "booking is roughly a coin-flip no-show (directive 015).")


def cmd_list(args) -> None:
    leads = _read_leads()
    if not args.all:
        leads = [lead for lead in leads if lead["stage"] not in CLOSED]
    if args.stage:
        leads = [lead for lead in leads if lead["stage"] == args.stage]
    if args.area:
        leads = [lead for lead in leads if lead["area"].lower() == args.area.lower()]
    if not leads:
        print("(no leads match)")
        return

    order = {stage: i for i, stage in enumerate(ALL_STAGES)}
    leads.sort(key=lambda lead: (-order.get(lead["stage"], 0), lead["next_action_date"] or "9999"))
    _print_table(leads)


def cmd_today(args) -> None:
    when = _valid_date(args.date) if args.date else _today()
    leads = [
        lead for lead in _read_leads()
        if lead["stage"] not in CLOSED
        and lead["next_action_date"]
        and lead["next_action_date"] <= when
    ]
    if not leads:
        print(f"Nothing due on or before {when}. Go knock on new doors — "
              "see directive 015 for the two good windows (10:00–11:30, 15:00–17:00).")
        return

    overdue = [lead for lead in leads if lead["next_action_date"] < when]
    print(f"DUE {when} — {len(leads)} lead(s)" + (f", {len(overdue)} OVERDUE" if overdue else ""))
    leads.sort(key=lambda lead: lead["next_action_date"])
    _print_table(leads, mark_overdue_before=when)


def cmd_show(args) -> None:
    leads = _read_leads()
    lead = _find(leads, args.id)
    print("=" * 64)
    print(f"#{lead['id']}  {lead['name']}")
    print("=" * 64)
    for key in ("area", "phone", "contact", "stage", "next_action_date", "created", "updated"):
        if lead[key]:
            print(f"  {key:<17} {lead[key]}")
    if lead["notes"]:
        print(f"  {'notes':<17} {lead['notes']}")

    touches = [t for t in _read_touches() if t["lead_id"] == lead["id"]]
    print(f"\n  History ({len(touches)} touch(es)):")
    for t in sorted(touches, key=lambda t: t["at"]):
        print(f"    {t['at']}  {t['outcome']:<14} {t['note']}")
    if len(touches) >= 6 and lead["stage"] not in CLOSED:
        print("\n  WARN: 6+ touches with no close. Directive 015 says park it as `cold` — "
              "further chasing costs you the referral.")


def cmd_stats(args) -> None:
    leads = _read_leads()
    if not leads:
        print("(pipeline is empty)")
        return

    counts = {stage: 0 for stage in ALL_STAGES}
    for lead in leads:
        counts[lead["stage"]] = counts.get(lead["stage"], 0) + 1

    # A lead that reached stage N necessarily passed through every earlier one,
    # so "reached N" counts everything at or beyond N. Measured on peak_stage,
    # not current stage, so a lead that got to demo_done and then died still
    # counts in the demo denominator — otherwise every loss quietly inflates the
    # close rate, which is the one number you must not be able to fool yourself
    # about.
    reached = {
        stage: sum(1 for lead in leads if _depth(_peak_of(lead)) >= _depth(stage))
        for stage in STAGES
    }
    reached["new"] = len(leads)

    print("=" * 64)
    print("OUTREACH FUNNEL")
    print("=" * 64)
    previous = None
    for stage in STAGES:
        n = reached[stage]
        rate = f"{n / previous:>6.0%} of previous" if previous else ""
        print(f"  {stage:<14} {n:>4}   {rate}")
        previous = n or None

    print("\n  Terminal")
    for stage in TERMINAL:
        print(f"  {stage:<14} {counts.get(stage, 0):>4}")

    booked, done, won = reached["demo_booked"], reached["demo_done"], reached["won"]
    print("\n  Key ratios (targets from directive 015)")
    if booked:
        print(f"  demo show-up   {done / booked:>6.0%}   target >70%")
    if done:
        print(f"  demo → won     {won / done:>6.0%}   target ~20-25% (1 in 4-5)")
    if not booked:
        print("  (not enough demos booked yet to judge — keep knocking)")


def _print_table(leads: list[dict], mark_overdue_before: str | None = None) -> None:
    print(f"\n  {'ID':<4} {'RESTAURANT':<26} {'AREA':<14} {'STAGE':<13} {'NEXT':<12} CONTACT")
    print("  " + "-" * 88)
    for lead in leads:
        nxt = lead["next_action_date"] or "-"
        if mark_overdue_before and lead["next_action_date"] and lead["next_action_date"] < mark_overdue_before:
            nxt += " !"
        contact = " ".join(x for x in (lead["contact"], lead["phone"]) if x)
        print(f"  {lead['id']:<4} {lead['name'][:26]:<26} {lead['area'][:14]:<14} "
              f"{lead['stage']:<13} {nxt:<12} {contact}")
    print()


# ── cli ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="register a new lead")
    p.add_argument("name")
    p.add_argument("--area", help="neighbourhood, for route planning")
    p.add_argument("--phone")
    p.add_argument("--contact", help="decision-maker's name")
    p.add_argument("--notes")
    p.add_argument("--next", help="next action date YYYY-MM-DD")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("log", help="record a visit or call")
    p.add_argument("id")
    p.add_argument("--outcome", required=True, choices=OUTCOMES)
    p.add_argument("--note")
    p.add_argument("--at", help="date of the touch (default: today)")
    p.add_argument("--next", help="next action date YYYY-MM-DD")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("stage", help="move a lead to a new stage")
    p.add_argument("id")
    p.add_argument("stage", choices=ALL_STAGES)
    p.add_argument("--next", help="next action date YYYY-MM-DD")
    p.add_argument("--note")
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("list", help="show the pipeline")
    p.add_argument("--stage", choices=ALL_STAGES)
    p.add_argument("--area")
    p.add_argument("--all", action="store_true", help="include lost/cold/disqualified")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("today", help="leads due for action")
    p.add_argument("--date", help="pretend it is this date (YYYY-MM-DD)")
    p.set_defaults(func=cmd_today)

    p = sub.add_parser("show", help="one lead with full touch history")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stats", help="funnel conversion")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

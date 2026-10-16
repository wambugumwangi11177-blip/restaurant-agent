"""
backend/owner/registry.py — every engine, and where the owner meets it (docs/v2/SPEC.md §2 principle 4).

"Nothing can be built and left unwired again." One entry per engine row of figure 1.3 (the keys are exactly
`execution/codemap.py::ENGINES`; a test keeps the two in step). Each entry says, in owner words:

  owner_name       what the owner calls it (§3.4 vocabulary)
  area             which of the six areas it lives in
  zone             where on Home it appears: pulse · costing_you_money · area · coming_up · os
  home_blocks      the block paths in the /owner/home payload that carry its output ("area.block" or a zone name)
  os_topics        the Ask LEVIII topics (owner/ask.py::topics — the five forms and the areas) that can answer questions about it
  report_sections  `period.section` keys in owner/reports.py::PLAN
  inputs           what the owner must have recorded for it to say anything (honest `no_data` otherwise)
  settings         the owner settings (owner/settings.py) it reads — empty means it reads none
  status           built · planned (engine not written yet; its blocks are honest `unavailable` placeholders)
  planned_in       the sprint that builds it (planned engines only)
  exemptions       surface -> written reason that this engine is correctly NOT on that surface

The coverage eval (`tests/evals/test_e5_coverage.py`) reads this file and the real composed payloads: a declared
block that is not in the payload, an OS topic that does not exist, or a report section that is not in PLAN is a
failure, and an engine missing from a surface without an exemption is a reported gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from owner import areas

SURFACES = ("home", "os", "reports")
ZONES = ("pulse", "costing_you_money", "area", "coming_up", "os")


@dataclass(frozen=True)
class Engine:
    key: str
    owner_name: str
    area: str
    zone: str
    home_blocks: tuple[str, ...] = ()
    os_topics: tuple[str, ...] = ()
    report_sections: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    settings: tuple[str, ...] = ()
    status: str = "built"
    planned_in: str | None = None
    built_blocks: tuple[str, ...] = ()         # an engine still `planned` may already have some of its Home blocks built
    exemptions: dict = field(default_factory=dict)

    def __post_init__(self):
        assert self.area in areas.AREAS, self.key
        assert self.zone in ZONES, self.key
        assert self.status in ("built", "planned"), self.key
        assert (self.status == "planned") == (self.planned_in is not None), self.key
        assert set(self.built_blocks) <= set(self.home_blocks), self.key
        assert not self.built_blocks or self.status == "planned", f"{self.key}: built_blocks only makes sense for a planned engine"
        assert set(self.exemptions) <= set(SURFACES), self.key
        assert all(self.exemptions.values()), f"{self.key}: an exemption needs a written reason"


ENGINES: tuple[Engine, ...] = (
    Engine("sales_summary", "Sales", "sales_dishes", "pulse",
           home_blocks=("pulse", "sales_dishes.seven_day"), os_topics=("revenue", "why", "compare"),
           report_sections=("daily.sales", "weekly.sales", "monthly.sales", "yearly.sales"),
           inputs=("orders from the till",)),
    Engine("revenue_forecast", "Sales forecast", "sales_dishes", "area",
           home_blocks=("sales_dishes.forecast",), os_topics=("revenue",),
           report_sections=("weekly.outlook",), inputs=("two weeks of sales",)),
    Engine("profit", "What each dish earns", "money", "area",
           home_blocks=("money.cost_dials", "sales_dishes.dishes_by_kes", "sales_dishes.delivery", "cash.below_menu_price"),
           os_topics=("profit", "compare"), report_sections=("monthly.costs", "monthly.dishes", "monthly.channels"),
           inputs=("orders from the till", "dish costs (recipes)"),
           settings=("food_cost_target_pct", "margin_floor_pct", "commission_uber_eats_pct", "commission_glovo_pct",
                     "commission_bolt_food_pct")),
    Engine("pricing", "Price ideas", "sales_dishes", "area",
           home_blocks=("sales_dishes.price_ideas",), os_topics=("pricing",), report_sections=("weekly.price_ideas",),
           inputs=("orders from the till", "dish costs (recipes)"),
           settings=("margin_floor_pct", "margin_target_pct", "price_step_kes", "max_raise_pct", "price_sensitivity")),
    Engine("menu", "Best and weakest dishes", "sales_dishes", "area",
           home_blocks=("sales_dishes.matrix",), os_topics=("menu",), report_sections=("weekly.dishes", "monthly.dishes"),
           inputs=("orders from the till", "dish costs (recipes)"),
           settings=("food_cost_target_pct", "popular_cutoff")),
    Engine("simulator", "What if I change a price", "sales_dishes", "area",
           home_blocks=("sales_dishes.simulator",), os_topics=("what_if",),
           inputs=("orders from the till", "dish costs (recipes)"),
           settings=("price_sensitivity", "offer_size_pct", "offer_lift_pct"),
           exemptions={"reports": "A what-if is a question you ask, not a figure to report; the numbers it moves are in the reports."}),
    Engine("inventory", "Time to reorder", "store", "area",
           home_blocks=("store.reorder",), os_topics=("stock",), report_sections=("daily.stock_today",),
           inputs=("stock counts", "stock movements")),
    Engine("custody", "Missing stock and handovers", "store", "area",
           home_blocks=("store.missing", "store.handover"), os_topics=("stock",),
           report_sections=("daily.things_to_check", "weekly.missing_stock"),
           inputs=("stock movements", "store-to-kitchen handovers"), settings=("missing_stock_flag_pct",)),
    Engine("cash", "Cash count check", "cash", "area",
           home_blocks=("cash.shifts", "cash.patterns"), os_topics=("cash",),
           report_sections=("daily.cash_check", "weekly.cash_check", "monthly.cash_check"),
           inputs=("cash drawer counts",), settings=("cash_tolerance_kes", "cash_tolerance_pct")),
    Engine("fraud", "Things to check at the till", "cash", "area",
           home_blocks=("cash.cancelled_sales",), os_topics=("things_to_check",), report_sections=("daily.things_to_check",),
           inputs=("orders from the till",)),
    Engine("kds", "Kitchen speed", "staff", "area",
           home_blocks=("staff.kitchen",), os_topics=("kitchen",), report_sections=("weekly.kitchen",),
           inputs=("kitchen preparation times",)),
    Engine("reservations", "Bookings", "sales_dishes", "coming_up",
           home_blocks=("coming_up.bookings",), os_topics=("bookings",), report_sections=("weekly.bookings",),
           inputs=("bookings",)),
    Engine("labor", "Wages", "staff", "area",
           home_blocks=("staff.wages", "staff.on_shift"), os_topics=("staff",),
           report_sections=("weekly.wages", "monthly.wages"), inputs=("staff shifts and hourly rates",),
           settings=("labour_target_pct", "overtime_after_hours")),
    Engine("supply_chain", "Suppliers", "store", "area",
           home_blocks=("store.suppliers", "coming_up.deliveries"), os_topics=("suppliers",),
           report_sections=("weekly.suppliers", "monthly.store"), inputs=("purchase orders and deliveries",)),
    Engine("marketing", "Winning guests back", "sales_dishes", "area",
           home_blocks=("sales_dishes.win_back",), os_topics=("win_back",), report_sections=("monthly.marketing",),
           inputs=("guest contacts and visits",), settings=("offer_size_pct", "offer_lift_pct")),
    Engine("roi", "What LEVIII saved you", "money", "area",
           home_blocks=("money.savings",), os_topics=("savings",), report_sections=("monthly.savings",),
           inputs=("ideas you approved",)),
    Engine("twin", "Next 30 days", "sales_dishes", "area",
           home_blocks=("sales_dishes.outlook",), os_topics=("revenue",), report_sections=("monthly.outlook",),
           inputs=("two weeks of sales",)),
    Engine("data_quality", "How complete your costs are", "permits", "area",
           home_blocks=("permits.data_trust",), os_topics=("data_trust",), report_sections=("monthly.data_trust",),
           inputs=("dish costs (recipes)",)),
    Engine("strategist", "Goal mode", "sales_dishes", "os",
           home_blocks=(), os_topics=("what_to_do",), report_sections=(),
           inputs=("all of the above",),
           exemptions={
               "home": "Goal mode is a conversation in Ask LEVIII (the 'what should I do' form, S5.1); Home already carries the ranked ideas it starts from (costing_you_money).",
               "reports": "A goal plan is built on request, not published on a schedule.",
           }),
    Engine("decisions", "What is costing you money", "money", "costing_you_money",
           home_blocks=("costing_you_money",), os_topics=("ops",), report_sections=("monthly.decisions",),
           inputs=("every engine above",), settings=("urgent_alerts_per_day",)),
    Engine("money", "Profit & Loss, costs covered, bills", "money", "area",
           home_blocks=("money.pnl", "money.breakeven", "money.bills", "money.spikes", "coming_up.bills",
                      "permits.licences", "coming_up.licences"),
           os_topics=("money",), report_sections=("monthly.pnl", "yearly.pnl"),
           inputs=("expenses", "recurring bills", "licences"),
           settings=("food_cost_target_pct", "prime_cost_target_pct", "labour_target_pct", "commission_uber_eats_pct", "commission_glovo_pct",
                     "commission_bolt_food_pct", "expense_spike_pct", "bill_reserve_kes", "licence_warning_days")),
    Engine("mpesa_match", "M-Pesa statement check", "cash", "pulse",
           home_blocks=("cash.mpesa",), os_topics=(), report_sections=(),
           inputs=("your M-Pesa statement",), status="planned", planned_in="S6.1–S6.2"),
    Engine("owner_settings", "Your targets", "permits", "area",
           home_blocks=("permits.settings",), os_topics=(), report_sections=("monthly.rules_used",),
           inputs=("none — defaults apply until you choose",),
           exemptions={"os": "Targets are changed on the settings sheet where the number is shown; Ask LEVIII reads them back as the rule used in an answer."}),
)

BY_KEY: dict[str, Engine] = {e.key: e for e in ENGINES}


def engines(status: str | None = None) -> tuple[Engine, ...]:
    return ENGINES if status is None else tuple(e for e in ENGINES if e.status == status)


# ── resolving the candidates the code map left open (S0.2 → S1.4) ─────────────
# Each real analysis module that is not a figure 1.3 row is either an engine above or, with a written reason,
# not one. `execution/codemap.py::INFRASTRUCTURE` carries the same reasons so the map and this file agree.
NOT_ENGINES: dict[str, str] = {
    "ai.ops_manager": "Resolved: 'restaurant health' — it is the health zone's rule set (tiles), not a separate figure; its output is the six tiles built from the area summaries.",
    "ai.creative": "Resolved: 'LEVIII's read' — the optional AI note on Home and in the monthly report; text only, every number must be backed (E3), so it has no figure of its own.",
    "ai.home_specialists": "Glue: turns engine output into cards for costing_you_money; the engines it calls are registered.",
    "ai.graph": "A tool the strategist uses (impact analysis); it feeds Goal mode and shows no figure to the owner.",
    "ai.enterprise": "Compare branches (OS 'compare' form, S5.1); applies only to multi-branch tenants, so it is registered with that form when it lands.",
    "ai.order_stock": "Order-time stock helper (deducts stock when a dish is sold); the stock figures it moves are shown by inventory and custody.",
}

# Blocks on Home that are composed, not computed by an engine of their own — each with the reason.
NOT_ENGINE_BLOCKS: dict[str, str] = {
    "health": "Six tiles built from the area summaries (the 'restaurant health' rule set, ai.ops_manager).",
    "read": "LEVIII's read — the optional AI note (ai.creative); text only, every number in it must be backed (E3).",
    "permits.till_connection": "Whether the till feed is connected and fresh (integration / observer source status), a fact about the data, not an analysis.",
}

"""
backend/ai/orchestrator/strategist.py
────────────────────────────────────────
The CEO / Strategy Agent — goal-driven orchestration (Phase 3).

Distinct from executive.py (which REACTS to events). This one takes a GOAL
("increase quarterly profit by KES 300k") and produces ONE prioritized strategy
by consulting the deterministic agents + the simulator + the knowledge graph as
read-only tools, then narrating a sequenced plan grounded in their numbers.

Design (carries directives/012's rules):
  • The LLM never computes. Its tools are the deterministic Decision Intelligence
    stream, the what-if simulator, the knowledge graph, and the revenue
    forecaster — it SELECTS, ORDERS and EXPLAINS; it never invents figures.
  • Every tool is READ-ONLY. Applying the strategy still goes through the
    existing human-approval hop (POST /ai/pricing/{id}/approve etc). The agent
    proposes; the owner disposes.
  • Grounding: every number in the final plan is checked against the numbers the
    tools actually returned; ungrounded figures are redacted (same guarantee as
    the WhatsApp orchestrator and dashboard narrator).
  • Degrades gracefully: with no LLM provider (or the feature off) it returns the
    deterministic top-ranked decisions as the plan — never an error.
  • Leaves a reasoning TRACE (which agents were consulted, in what order, why),
    persisted to AgentAuditLog + AgentExecution, and meters tokens to TokenUsage.
"""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy.orm import Session

import models
from time_utils import utcnow

logger = logging.getLogger("ai.strategist")

PROMPT_VERSION = "strategy.v1"
MAX_STRATEGY_TURNS = 6

SYSTEM_PROMPT = (
    "You are the CEO's operations strategist for a single restaurant. You are given a "
    "GOAL. Build ONE prioritized strategy to reach it.\n"
    "Rules:\n"
    "- Use the tools to gather facts. list_decisions gives you the already-ranked, "
    "already-costed recommendations from every specialist agent. simulate lets you test a "
    "price/promo/cost change. graph_impact shows what a supplier/ingredient/dish affects. "
    "revenue_forecast gives the near-term revenue outlook.\n"
    "- NEVER invent numbers. Only cite figures the tools returned. Do the reasoning, not the "
    "arithmetic.\n"
    "- When you have enough, reply with a final JSON object ONLY, no prose around it:\n"
    '{"headline": "one-sentence strategy", '
    '"steps": [{"action": "what to do", "why": "reason citing tool data", '
    '"expected_impact": "e.g. +KES 40,000/mo or qualitative"}], '
    '"risks": ["key risk", "..."]}\n'
    "Order steps by priority (highest-impact, lowest-risk first). 3-6 steps."
)


# ─────────────────────────────────────────────────────────────────────────────
# Read-only tools exposed to the LLM
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_decisions",
        "description": "Every specialist agent's recommendations, already ranked and costed "
                       "(pricing, inventory, supply-chain, menu, labor, marketing).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "simulate",
        "description": "Project a proposed change before committing. type is 'price_change', "
                       "'promo' or 'cost_change'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["price_change", "promo", "cost_change"]},
                "item_id": {"type": "integer"},
                "new_price": {"type": "integer", "description": "new price in cents (price_change)"},
                "change_pct": {"type": "number", "description": "percent price change (price_change)"},
                "discount_pct": {"type": "number", "description": "promo discount percent (promo)"},
                "new_cost": {"type": "integer", "description": "new ingredient cost in cents (cost_change)"},
            },
            "required": ["type", "item_id"],
        },
    },
    {
        "name": "graph_impact",
        "description": "Downstream impact of a 'supplier', 'ingredient' or 'menu_item' across "
                       "the business — which dishes/categories and how much revenue it touches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "enum": ["supplier", "ingredient", "menu_item"]},
                "id": {"type": "integer"},
            },
            "required": ["entity", "id"],
        },
    },
    {
        "name": "revenue_forecast",
        "description": "Near-term revenue outlook: trend, week-over-week growth, and the 7-day forecast.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def _tool_list_decisions(db: Session, restaurant_id: int, **_) -> dict:
    from ai.decisions import get_ranked_decisions
    data = get_ranked_decisions(db, restaurant_id)
    # Trim to the salient, terse fields to control tokens.
    return {
        "summary": data["summary"],
        "decisions": [
            {
                "rank": d["rank"], "category": d["category"], "action": d["action"],
                "priority_score": d["priority_score"], "confidence_pct": d["confidence_pct"],
                "impact_cents_month": d["impact_cents_month"], "risk": d["risk"],
                "difficulty": d["difficulty"], "entity_id": d.get("entity_id"),
            }
            for d in data["decisions"][:10]
        ],
    }


def _tool_simulate(db: Session, restaurant_id: int, **kwargs) -> dict:
    from ai.simulation import run_simulation
    return run_simulation(db, restaurant_id, kwargs)


def _tool_graph_impact(db: Session, restaurant_id: int, entity: str = "", id: int = 0, **_) -> dict:
    from ai.graph import get_impact
    report = get_impact(db, restaurant_id, entity, id)
    report.pop("edges", None)   # drop the verbose edge list; keep summary + affected
    return report


def _tool_revenue_forecast(db: Session, restaurant_id: int, **_) -> dict:
    from ai.revenue_forecaster import get_revenue_forecast
    data = get_revenue_forecast(db, restaurant_id)
    # Keep the forecast-salient keys only.
    return {k: data[k] for k in ("summary", "trends", "forecast") if isinstance(data, dict) and k in data}


_DISPATCH = {
    "list_decisions": _tool_list_decisions,
    "simulate": _tool_simulate,
    "graph_impact": _tool_graph_impact,
    "revenue_forecast": _tool_revenue_forecast,
}


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_strategy(db: Session, restaurant_id: int, goal: str, timeframe: str = "") -> dict:
    """
    Produce one prioritized strategy for `goal`. LLM-backed when a provider is
    configured and the feature is on; otherwise a deterministic fallback built
    from the ranked Decision Intelligence stream.
    """
    goal = (goal or "").strip()
    if not goal:
        return {"available": False, "error": "Provide a goal, e.g. 'increase monthly profit by KES 100,000'."}

    import feature_flags
    from ai import llm_client

    llm_ready = (
        feature_flags.is_enabled("strategy_agent")
        and feature_flags.is_enabled("ai_narration")
        and llm_client.is_available()
    )
    if not llm_ready:
        return _deterministic_strategy(db, restaurant_id, goal, timeframe)

    return _llm_strategy(db, restaurant_id, goal, timeframe)


def plan(db: Session, restaurant_id: int, goal: str, horizon_weeks: int = 4) -> dict:
    """
    Autonomous planning (Phase 9): turn a goal into a time-phased, monitored plan
    — a ranked decision per week, each with a scheduled check-in and, where it's a
    price move, a simulation of its expected effect. Deterministic and always
    available (no LLM required); the Workflow Engine can execute/track each step.
    """
    from datetime import timedelta
    goal = (goal or "").strip()
    if not goal:
        return {"available": False, "error": "Provide a goal to plan for."}

    horizon_weeks = max(1, min(12, int(horizon_weeks)))
    from ai.decisions import get_ranked_decisions
    decisions = get_ranked_decisions(db, restaurant_id)["decisions"][:horizon_weeks]

    today = utcnow().date()
    weeks = []
    total_impact = 0
    for i, d in enumerate(decisions):
        check_in = today + timedelta(days=(i + 1) * 7)
        entry = {
            "week": i + 1,
            "check_in_date": check_in.isoformat(),
            "decision": {
                "action": d["action"], "category": d["category"],
                "rationale": d["rationale"], "priority_score": d["priority_score"],
                "impact_cents_month": d["impact_cents_month"],
            },
        }
        # For a price move, attach a simulation so the plan shows expected effect.
        if d["category"] == "pricing" and d.get("entity_id") and d.get("meta", {}).get("price_change_pct"):
            from ai.simulation import run_simulation
            sim = run_simulation(db, restaurant_id, {
                "type": "price_change", "item_id": d["entity_id"],
                "change_pct": d["meta"]["price_change_pct"],
            })
            if sim.get("available"):
                entry["simulation"] = {
                    "verdict": sim["verdict"],
                    "profit_cents_month": sim["deltas"]["profit_cents_month"],
                    "confidence_pct": sim["confidence_pct"],
                }
        if d.get("impact_cents_month"):
            total_impact += d["impact_cents_month"]
        weeks.append(entry)

    return {
        "available": True,
        "goal": goal,
        "horizon_weeks": horizon_weeks,
        "generated_from": today.isoformat(),
        "weeks": weeks,
        "total_expected_impact_cents": total_impact,
        "note": "A monitored, week-by-week plan. Each step is owner-approved before it acts.",
    }


def _deterministic_strategy(db: Session, restaurant_id: int, goal: str, timeframe: str) -> dict:
    """Fallback: the top ranked decisions as a plan. No LLM, always works."""
    from ai.decisions import get_ranked_decisions
    data = get_ranked_decisions(db, restaurant_id)
    top = data["decisions"][:6]
    steps = [
        {
            "action": d["action"],
            "why": d["rationale"],
            "expected_impact": (f"+KES {d['impact_cents_month'] // 100:,}/mo"
                                if d.get("quantified") and d.get("impact_cents_month") else "not quantified"),
            "priority_score": d["priority_score"],
            "category": d["category"],
        }
        for d in top
    ]
    return {
        "available": True,
        "mode": "deterministic",
        "goal": goal,
        "timeframe": timeframe,
        "strategy": {
            "headline": (f"Work the {len(steps)} highest-value open decisions"
                         if steps else "No open decisions right now."),
            "steps": steps,
            "risks": [],
        },
        "ranked_decisions": data["summary"],
        "trace": [{"step": "ranked deterministic decisions", "tool": "list_decisions"}],
        "note": "LLM strategy is off or unavailable — showing the deterministic ranked plan.",
    }


def _llm_strategy(db: Session, restaurant_id: int, goal: str, timeframe: str) -> dict:
    from ai import llm_client, pii_scrub
    from ai.reasoning import grounding
    from ai.llm_client import TIER_HIGH

    user_msg = f"GOAL: {goal}"
    if timeframe:
        user_msg += f"\nTIMEFRAME: {timeframe}"
    messages = [{"role": "user", "content": pii_scrub.scrub_for_llm(user_msg)}]

    trace: list[dict] = []
    grounded_numbers: set = set()
    tokens_in = tokens_out = 0
    last_model = None
    start = time.perf_counter()

    final_text = ""
    for _turn in range(MAX_STRATEGY_TURNS):
        response = llm_client.chat_with_tools(
            messages=messages, tools=TOOLS, system=SYSTEM_PROMPT,
            tier=TIER_HIGH, max_tokens=1500,
        )
        tokens_in += response.usage.input_tokens
        tokens_out += response.usage.output_tokens
        last_model = response.model

        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            fn = _DISPATCH.get(block.name)
            try:
                result = fn(db, restaurant_id, **(block.input or {})) if fn else {"error": f"unknown tool {block.name}"}
            except Exception as exc:  # noqa: BLE001 — a bad tool call must not kill the run
                result = {"error": str(exc)}
            result_text = json.dumps(result, default=str)
            result_text = pii_scrub.scrub_for_llm(result_text)
            grounded_numbers |= grounding.collect_payload_numbers(result_text)
            trace.append({
                "tool": block.name,
                "input": block.input or {},
                "summary": _summarize_tool_result(block.name, result),
            })
            tool_results.append({
                "type": "tool_result", "tool_use_id": block.id, "content": result_text,
            })
        messages.append({"role": "user", "content": tool_results})
    else:
        final_text = final_text or ""

    strategy = _parse_strategy(final_text)
    # Ground every step's free text against the numbers the tools returned.
    strategy = _ground_strategy(strategy, grounded_numbers, grounding)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    _persist(db, restaurant_id, goal, strategy, trace, last_model,
             tokens_in, tokens_out, elapsed_ms)

    return {
        "available": True,
        "mode": "llm",
        "goal": goal,
        "timeframe": timeframe,
        "strategy": strategy,
        "trace": trace,
        "tokens": {"input": tokens_in, "output": tokens_out, "model": last_model},
    }


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _summarize_tool_result(name: str, result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)[:200]
    if result.get("error"):
        return f"error: {result['error']}"
    if name == "list_decisions":
        s = result.get("summary", {})
        return f"{s.get('total_decisions', 0)} decisions, top: {s.get('top_action')}"
    if name == "simulate":
        return f"verdict {result.get('verdict')}, profit Δ {result.get('deltas', {}).get('profit_cents_month')}c/mo"
    if name == "graph_impact":
        s = result.get("summary", {})
        return f"{s.get('affected_dishes', 0)} dishes, KES {s.get('revenue_at_risk_30d_cents', 0) // 100:,} at risk"
    if name == "revenue_forecast":
        return "revenue outlook returned"
    return "ok"


def _parse_strategy(text: str) -> dict:
    """Parse the model's final JSON; fall back to treating the text as a headline."""
    text = (text or "").strip()
    # Strip a ```json fence if present.
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                obj.setdefault("headline", "")
                obj.setdefault("steps", [])
                obj.setdefault("risks", [])
                return obj
        except json.JSONDecodeError:
            pass
    return {"headline": text[:280] or "No strategy produced.", "steps": [], "risks": []}


def _ground_strategy(strategy: dict, grounded: set, grounding) -> dict:
    """Redact any ungrounded figure from the human-readable strategy text."""
    def clean(s):
        if not isinstance(s, str):
            return s
        red, _ung = grounding.redact_free_text(s, grounded)
        return red

    strategy["headline"] = clean(strategy.get("headline", ""))
    for step in strategy.get("steps", []):
        if isinstance(step, dict):
            for k in ("action", "why", "expected_impact"):
                if k in step:
                    step[k] = clean(step[k])
    strategy["risks"] = [clean(r) for r in strategy.get("risks", [])]
    return strategy


def _persist(db, restaurant_id, goal, strategy, trace, model, tokens_in, tokens_out, elapsed_ms):
    """Write the reasoning trace to the audit log + execution + token meter."""
    from ai.evaluation.tracker import write_audit_log
    try:
        write_audit_log(
            db, restaurant_id, "strategy_generated", "strategist",
            reasoning=strategy.get("headline", "")[:5000],
            data_sources=[t["tool"] for t in trace],
            approved_by="ai",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("strategy audit log failed: %s", exc)

    # Token metering + execution record on their own session so they never
    # interfere with the request transaction (mirrors the WhatsApp orchestrator).
    try:
        from database import SessionLocal
        s = SessionLocal()
        try:
            s.add(models.TokenUsage(
                restaurant_id=restaurant_id, llm_model=model,
                prompt_version=PROMPT_VERSION,
                input_tokens=tokens_in, output_tokens=tokens_out,
            ))
            s.add(models.AgentExecution(
                restaurant_id=restaurant_id, agent_name="strategist",
                function_name="run_strategy", success=True,
                execution_ms=elapsed_ms, records_processed=len(trace),
                triggered_by="api",
            ))
            s.commit()
        finally:
            s.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("strategy metering failed: %s", exc)

"""Bounded, scrubbed and metered optional narration for owner chat/reports.

Only text leaves this boundary. No tools or operational write capabilities are
provided. Numeric verification remains the caller's job; it is not a complete
semantic or prompt-injection defense.
"""
from fastapi import HTTPException

import models
from ai import llm_client, pii_scrub, spend_cap
from ai.cost_model import cost_usd


def narrate(db, user, restaurant_id, messages, system, max_tokens, prompt_version):
    # Lock the tenant while checking and metering so simultaneous chat/report
    # requests cannot independently spend the same remaining estimated budget.
    db.query(models.Tenant).filter_by(id=user.tenant_id).with_for_update().one()
    restaurant_ids = [row[0] for row in db.query(models.Restaurant.id).filter_by(tenant_id=user.tenant_id)]
    if restaurant_id not in restaurant_ids:
        raise HTTPException(404, "Restaurant not found")
    spent = sum(spend_cap.today_spend_usd(db, rid) for rid in restaurant_ids)
    known_names = pii_scrub.known_names_for_restaurant(db, restaurant_id)
    clean_system = pii_scrub.scrub_for_llm(system, known_names)
    clean_messages = [{"role": m["role"], "content": pii_scrub.scrub_for_llm(m["content"], known_names)} for m in messages]
    # UTF-8 bytes overestimate ordinary text tokens. Include a framing margin.
    input_bound = len(clean_system.encode()) + sum(len(m['content'].encode()) for m in clean_messages) + 1024
    estimate = cost_usd(llm_client.model_for_tier('medium'), input_bound, max_tokens)
    if spent + estimate >= spend_cap.DAILY_LLM_SPEND_CAP_USD:
        raise HTTPException(429, "Daily estimated AI budget reached. Deterministic reports remain available.")
    result = llm_client.chat_with_usage(clean_messages, system=clean_system,
                                        max_tokens=max_tokens, tier='medium', temperature=0)
    # Meter paid output even if a later grounding check rejects its content.
    db.add(models.TokenUsage(restaurant_id=restaurant_id, llm_model=result.model,
                            input_tokens=result.usage.input_tokens,
                            output_tokens=result.usage.output_tokens,
                            prompt_version=prompt_version))
    db.commit()
    return pii_scrub.scrub_for_llm(result.text, known_names)

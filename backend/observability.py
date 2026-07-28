"""
backend/observability.py
─────────────────────────
One helper for the pattern this codebase uses everywhere: an optional path
failed, the caller should keep going, but the failure must not vanish.

The motivating case is ai/roi/savings.py, which had seven `except Exception:
pass` handlers and imported no logger at all. Each wrapped one contributor to
the ROI figure (profit leaks, inventory waste, no-shows, labor overtime, kitchen
capacity, net-ROI economics). If one raised, that category silently contributed
zero and the dashboard rendered a confidently wrong number — lower than reality,
with no log line, no metric, and no way to notice. For a figure shown to paying
customers as "what the AI saved you", silent partial failure is worse than a
visible error.

The intent behind those handlers was right: ROI must degrade, not crash. What
was missing is that degrading is an EVENT, not a non-event. So:

    try:
        ...
    except Exception as exc:
        degraded("roi.inventory_waste", exc)

logs at WARNING with a traceback and increments a per-component counter that
surfaces on /metrics. The behaviour is identical — the caller still continues —
but the failure is now countable, alertable, and greppable by component.

Why a counter and not just a log line: a log line is only found by someone
already looking. `app_degradations_total{component="roi.inventory_waste"}`
climbing off zero is something a dashboard shows you without being asked, which
is the difference between "we could have found it" and "we found it".
"""

import logging

logger = logging.getLogger(__name__)


def degraded(component: str, exc: BaseException, **context) -> None:
    """
    Record that `component` failed and the caller is continuing without it.

    Never raises — a failure in the failure handler must not replace the original
    error with a more confusing one. `context` is merged into the structured log
    record (logging_config.JsonFormatter passes extras through to the JSON line),
    so callers can attach ids: degraded("roi.profit", exc, restaurant_id=3).
    """
    try:
        logger.warning(
            "degraded: %s unavailable (%s: %s)",
            component, exc.__class__.__name__, exc,
            exc_info=True,
            extra={"component": component, **context},
        )
    except Exception:  # pragma: no cover — logging itself is broken
        pass

    try:
        import metrics
        metrics.record_degradation(component)
    except Exception:  # pragma: no cover — metrics must never break a request
        pass

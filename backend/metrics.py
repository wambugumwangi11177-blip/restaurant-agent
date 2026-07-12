"""
backend/metrics.py
───────────────────
Dependency-free, in-process metrics in Prometheus text-exposition format, served
at GET /metrics and fed by TimingMiddleware. Kept hand-rolled (no prometheus_client
dependency) in the spirit of this codebase's minimal-deps approach.

Honest scope: counters are PROCESS-LOCAL. With gunicorn --workers 1 (current) that
is the whole picture; under multiple workers each exposes its own slice and a real
setup needs a shared/multiprocess collector — the same shared-store caveat as
rate_limit.py. Documented rather than hidden.
"""

import threading

_lock = threading.Lock()
_requests_total: dict[tuple[str, str], int] = {}   # (method, status_class) -> count
_latency_sum = 0.0
_latency_count = 0


def record_request(method: str, status_code: int, duration_s: float) -> None:
    global _latency_sum, _latency_count
    status_class = f"{status_code // 100}xx"
    with _lock:
        key = (method, status_class)
        _requests_total[key] = _requests_total.get(key, 0) + 1
        _latency_sum += duration_s
        _latency_count += 1


def render() -> str:
    """Prometheus text-exposition format (v0.0.4)."""
    lines = [
        "# HELP app_requests_total Total HTTP requests by method and status class.",
        "# TYPE app_requests_total counter",
    ]
    with _lock:
        for (method, status_class), count in sorted(_requests_total.items()):
            lines.append(
                f'app_requests_total{{method="{method}",status="{status_class}"}} {count}'
            )
        lines.append("# HELP app_request_latency_seconds_sum Sum of request durations in seconds.")
        lines.append("# TYPE app_request_latency_seconds_sum counter")
        lines.append(f"app_request_latency_seconds_sum {_latency_sum:.6f}")
        lines.append("# HELP app_request_latency_seconds_count Number of requests measured.")
        lines.append("# TYPE app_request_latency_seconds_count counter")
        lines.append(f"app_request_latency_seconds_count {_latency_count}")
    return "\n".join(lines) + "\n"


def reset() -> None:
    """Test helper — clear all counters."""
    global _latency_sum, _latency_count
    with _lock:
        _requests_total.clear()
        _latency_sum = 0.0
        _latency_count = 0

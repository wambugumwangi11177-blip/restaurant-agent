"""
Prometheus /metrics endpoint (Phase 4, 2026-07-12): request counters + latency,
fed by TimingMiddleware, in valid exposition format.
"""

import metrics


def test_metrics_endpoint_exposes_counters(client, db_session):
    metrics.reset()
    # Generate some traffic through the middleware.
    client.get("/health/")
    client.get("/health/")
    client.get("/does-not-exist")  # a 404

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text

    # Exposition format basics.
    assert "# TYPE app_requests_total counter" in body
    assert 'app_requests_total{method="GET",status="2xx"}' in body
    assert "app_request_latency_seconds_count" in body


def test_record_request_accumulates():
    metrics.reset()
    metrics.record_request("GET", 200, 0.01)
    metrics.record_request("GET", 200, 0.02)
    metrics.record_request("POST", 500, 0.05)
    out = metrics.render()
    assert 'app_requests_total{method="GET",status="2xx"} 2' in out
    assert 'app_requests_total{method="POST",status="5xx"} 1' in out
    assert "app_request_latency_seconds_count 3" in out

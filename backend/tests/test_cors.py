"""
CORS tightening (audit finding, §2.7). allow_methods/allow_headers used to be
["*"] paired with allow_credentials=True — broader than the API actually
needs. These tests prove the narrowed allowlist still permits everything the
frontend uses (an actually-used method, the Authorization header) from an
allowed origin, and that the wildcard is actually gone (not just cosmetically
narrowed while still matching everything).
"""

ALLOWED_ORIGIN = "http://localhost:3000"


def test_preflight_allows_an_actually_used_method_and_header(client):
    resp = client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    allowed_methods = resp.headers.get("access-control-allow-methods", "")
    assert "GET" in allowed_methods
    allowed_headers = resp.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed_headers


def test_wildcard_method_is_no_longer_allowed(client):
    """A method this API never defines (TRACE) must not be echoed back —
    proves the allowlist is a real list, not a wildcard in disguise."""
    resp = client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "TRACE",
        },
    )
    # starlette's CORSMiddleware rejects a preflight for a disallowed method
    # with 400, rather than a 200 that happens to omit it from the header.
    assert resp.status_code == 400

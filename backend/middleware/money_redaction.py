"""Strip money keys from JSON responses for storekeeper and kitchen callers."""
import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

import auth
import models
from money_visibility import hides_money, scrub_money

logger = logging.getLogger("restaurant_agent.money")


def _user_for_request(request):
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = auth.jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    except auth.JWTError:
        return None
    email = payload.get("sub")
    if not email:
        return None
    import database
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None or user.is_active is False:
            return None
        if payload.get("ver", 0) != (user.token_version or 0):
            return None
        # Plain snapshot so the closed session is not touched again.
        return type("MoneyViewer", (), {"role": user.role, "staff_role": user.staff_role})()
    except Exception as exc:
        logger.warning("money redaction lookup skipped: %s", exc)
        return None
    finally:
        db.close()


class MoneyRedactionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response
        user = _user_for_request(request)
        if user is None or not hides_money(user, request.url.path):
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type="application/json",
            )
        cleaned = json.dumps(scrub_money(payload)).encode("utf-8")
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(
            content=cleaned,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )

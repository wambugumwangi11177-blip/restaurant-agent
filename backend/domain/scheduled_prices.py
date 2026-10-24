"""Explicit owner-set prices. Order lines retain their immutable sold-price snapshot.

Quotes are signed with a key and audience that login tokens do not use, and they
are attached only when a scheduled price applies. An expired or unreadable quote
is re-priced from the current menu so a till left open, or an offline replay,
does not get stuck. A missing quote still has to be reloaded when a scheduled
price applies, so the cashier confirms that price before the first send.
"""
import hashlib
import hmac
import os
from datetime import timedelta

import models
from time_utils import EAT_OFFSET, eat_date

QUOTE_AUDIENCE = "leviii-menu-price"
QUOTE_TTL = timedelta(minutes=60)


def quote_key() -> str:
    """Signing key for menu quotes. Never the login secret, so a quote cannot be presented as a session."""
    explicit = os.getenv("MENU_QUOTE_SECRET", "").strip()
    if explicit:
        return explicit
    import auth
    return hmac.new(auth.SECRET_KEY.encode(), b"leviii-menu-price-v1", hashlib.sha256).hexdigest()


def daypart(at):
    hour = (at + EAT_OFFSET).hour
    return 'late' if hour < 6 or hour >= 22 else 'breakfast' if hour < 11 else 'lunch' if hour < 15 else 'afternoon' if hour < 18 else 'dinner'


def prices(db, rid, channel, at):
    day = eat_date(at)
    rules = db.query(models.ScheduledMenuPrice).filter(
        models.ScheduledMenuPrice.restaurant_id == rid, models.ScheduledMenuPrice.is_active.is_(True),
        models.ScheduledMenuPrice.starts_on <= day,
        (models.ScheduledMenuPrice.ends_on.is_(None)) | (models.ScheduledMenuPrice.ends_on >= day),
        models.ScheduledMenuPrice.channel.in_(['all', channel]),
        models.ScheduledMenuPrice.daypart.in_(['all', daypart(at)])).all()
    rules.sort(key=lambda r: (int(r.channel != 'all') + int(r.daypart != 'all'), r.id))
    return {r.menu_item_id: r.price_cents for r in rules}


def _sign(rid, item_id, channel, price, at):
    import auth
    return auth.jwt.encode({
        "kind": "menu_price",
        "aud": QUOTE_AUDIENCE,
        "rid": rid,
        "item": item_id,
        "channel": channel,
        "price": price,
        "exp": at + QUOTE_TTL,
    }, quote_key(), algorithm=auth.ALGORITHM)


def quoted_menu(db, rid, channel, items, at):
    """Base `price` stays the stored menu price. `effective_price` is what the till charges now."""
    import schemas
    overrides = prices(db, rid, channel, at)
    out = []
    for item in items:
        effective = overrides.get(item.id, item.price)
        update = {"price": item.price, "effective_price": effective}
        if item.id in overrides:
            update["price_quote"] = _sign(rid, item.id, channel, effective, at)
        out.append(schemas.MenuItem.model_validate(item).model_copy(update=update))
    return out


def _read_quote(token):
    """Return the quote claims, or ('expired'|'invalid', None)."""
    import auth
    from jose.exceptions import ExpiredSignatureError
    try:
        quoted = auth.jwt.decode(token, quote_key(), algorithms=[auth.ALGORITHM], audience=QUOTE_AUDIENCE)
    except ExpiredSignatureError:
        return "expired", None
    except auth.JWTError:
        return "invalid", None
    if quoted.get("kind") != "menu_price":
        return "invalid", None
    return "ok", quoted


def checkout_prices(db, rid, channel, lines, at):
    import auth
    from fastapi import HTTPException
    current = prices(db, rid, channel, at)
    resolved = dict(current)
    for line in lines:
        if not line.price_quote:
            if line.menu_item_id in current:
                raise HTTPException(409, "Reload the menu to confirm the scheduled price before ordering")
            continue
        status, quoted = _read_quote(line.price_quote)
        if status == "expired":
            # The hour the cashier saw has passed. Charge the price that applies now
            # (the scheduled price when one is active, otherwise the base menu price).
            continue
        if status != "ok":
            if line.menu_item_id in current:
                raise HTTPException(409, "Menu quote expired or invalid. Reload the menu and confirm your order.")
            resolved.pop(line.menu_item_id, None)
            continue
        try:
            if quoted.get("rid") != rid or quoted.get("item") != line.menu_item_id or quoted.get("channel") != channel:
                raise ValueError("Wrong quote scope")
            resolved[line.menu_item_id] = quoted["price"]
        except (auth.JWTError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, "Menu quote expired or invalid. Reload the menu and confirm your order.") from exc
    return resolved

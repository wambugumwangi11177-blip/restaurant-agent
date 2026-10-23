"""Explicit owner-set prices. Order lines retain their immutable sold-price snapshot."""
import models
from datetime import timedelta
from time_utils import EAT_OFFSET, eat_date


def daypart(at):
    hour = (at+EAT_OFFSET).hour
    return 'late' if hour < 6 or hour >= 22 else 'breakfast' if hour < 11 else 'lunch' if hour < 15 else 'afternoon' if hour < 18 else 'dinner'


def prices(db, rid, channel, at):
    day = eat_date(at)
    rules = db.query(models.ScheduledMenuPrice).filter(
        models.ScheduledMenuPrice.restaurant_id == rid, models.ScheduledMenuPrice.is_active.is_(True),
        models.ScheduledMenuPrice.starts_on <= day,
        (models.ScheduledMenuPrice.ends_on.is_(None)) | (models.ScheduledMenuPrice.ends_on >= day),
        models.ScheduledMenuPrice.channel.in_(['all', channel]),
        models.ScheduledMenuPrice.daypart.in_(['all', daypart(at)])).all()
    rules.sort(key=lambda r: (int(r.channel != 'all')+int(r.daypart != 'all'), r.id))
    return {r.menu_item_id: r.price_cents for r in rules}


def quoted_menu(db, rid, channel, items, at):
    import auth
    import schemas
    overrides=prices(db,rid,channel,at)
    out=[]
    for item in items:
        price=overrides.get(item.id,item.price)
        token=auth.jwt.encode({'kind':'menu_price','rid':rid,'item':item.id,'channel':channel,
                               'price':price,'exp':at+timedelta(minutes=60)},auth.SECRET_KEY,algorithm=auth.ALGORITHM)
        out.append(schemas.MenuItem.model_validate(item).model_copy(update={'price':price,'price_quote':token}))
    return out


def checkout_prices(db,rid,channel,lines,at):
    import auth
    from fastapi import HTTPException
    resolved=prices(db,rid,channel,at)
    for line in lines:
        if not line.price_quote:
            if line.menu_item_id in resolved:
                raise HTTPException(409,'Reload the menu to confirm the scheduled price before ordering')
            continue
        try:
            quoted=auth.jwt.decode(line.price_quote,auth.SECRET_KEY,algorithms=[auth.ALGORITHM])
            if quoted.get('kind')!='menu_price' or quoted.get('rid')!=rid or quoted.get('item')!=line.menu_item_id or quoted.get('channel')!=channel:
                raise ValueError('Wrong quote scope')
            resolved[line.menu_item_id]=quoted['price']
        except (auth.JWTError,ValueError,KeyError) as exc:
            raise HTTPException(409,'Menu quote expired or invalid. Reload the menu and confirm your order.') from exc
    return resolved
